# ad_post.py - Production Ready

import frappe
import logging
import json
import os
from frappe import _
from frappe.model.document import Document
from frappe.utils import now, get_datetime
from ads_manager.ads_manager.providers.meta_ads import MetaAdsProvider

logger = logging.getLogger(__name__)


class AdPost(Document):
    """
    Ad Post Document
    Orchestrates media upload → creative creation → ad creation on Meta
    """

    def validate(self):
        """Validate document before save"""
        self._validate_required_fields()
        self._validate_status()
        self._validate_page_selection()
    
    def before_save(self):
        """Update status before save"""
        self.status = "ACTIVE" if self.enable else "PAUSED"
    
    def after_insert(self):
        """Create ad on Meta after document insert"""
        if not self.ad_id:
            self._create_ad_on_meta()
    
    def on_update(self):
        """Handle updates to existing ads"""
        if self.ad_id and self.has_value_changed('status'):
            self._update_ad_status()
    
    def _validate_required_fields(self):
        """Validate all required fields are present"""
        required_fields = {
            'ad_name': 'Ad Name',
            'ad_set': 'Ad Set',
            'ads_account': 'Ads Account',
            'campaign': 'Campaign',
            'select_facebook_page': 'Facebook Page'
        }
        
        for field, label in required_fields.items():
            if not self.get(field):
                frappe.throw(_("{0} is required").format(label))
        
        # Validate child tables
        if not self.ad_creative or len(self.ad_creative) == 0:
            frappe.throw(_("At least one Ad Creative is required"))
        
        if not self.media or len(self.media) == 0:
            frappe.throw(_("At least one Media file is required"))
    
    def _validate_status(self):
        """Validate status field"""
        valid_statuses = ['ACTIVE', 'PAUSED', 'DELETED', 'ARCHIVED']
        if self.status and self.status not in valid_statuses:
            frappe.throw(_("Invalid status. Must be one of: {0}").format(', '.join(valid_statuses)))
    
    def _validate_page_selection(self):
        """Validate that selected Facebook page belongs to the account"""
        if not self.ads_account or not self.select_facebook_page:
            return
        
        try:
            integration = frappe.get_doc("Ads Account Integration", self.ads_account)
            pages = integration.get("fb_pages", [])
            
            # Extract page_id from label format "Page Name (page_id)"
            selected_page_id = self._extract_page_id_from_label(self.select_facebook_page)
            
            page_ids = [page.page_id for page in pages if page.page_id]
            
            if selected_page_id not in page_ids:
                frappe.throw(_("Selected Facebook Page does not belong to this account"))
        
        except frappe.DoesNotExistError:
            frappe.throw(_("Ads Account Integration not found"))
    
    def _extract_page_id_from_label(self, label):
        """Extract page_id from label format 'Page Name (page_id)'"""
        if '(' in label and ')' in label:
            return label.split('(')[-1].rstrip(')')
        return label
    
    def _get_page_access_token(self, page_id):
        """Get page access token for the given page"""
        try:
            integration = frappe.get_doc("Ads Account Integration", self.ads_account)
            
            # Check if token is stored in fb_pages child table
            for page in integration.get("fb_pages", []):
                if page.page_id == page_id:
                    # Try to get the password field value
                    stored_token = page.get("page_access_token")
                    if stored_token:
                        logger.info(f"✓ Using stored page access token for page {page_id}")
                        return stored_token
                    else:
                        logger.warning(f"Page {page_id} found but no access token stored")
                        break
            
            # If not stored, fetch it using the user's access token
            logger.info(f"Fetching page access token for page {page_id} from Meta API")
            
            user_token = integration.get_access_token()
            if not user_token:
                logger.error("No user access token available in integration")
                frappe.throw(_("User access token not found. Please reconnect the account."))
            
            import requests
            url = f"https://graph.facebook.com/v24.0/{page_id}"
            params = {
                "access_token": user_token,
                "fields": "access_token"
            }
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            page_token = data.get("access_token")
            
            if page_token:
                logger.info(f"✓ Fetched page access token for page {page_id}")
                
                # Store it for future use
                for page in integration.get("fb_pages", []):
                    if page.page_id == page_id:
                        frappe.db.set_value(
                            'Facebook Pages',
                            page.name,
                            'access_token',
                            page_token
                        )
                        frappe.db.commit()
                        logger.info(f"✓ Saved page access token to database")
                        break
                
                return page_token
            else:
                logger.error(f"No page access token returned for page {page_id}")
                frappe.throw(_("Failed to get page access token from Meta"))
                
        except requests.RequestException as e:
            logger.error(f"Network error fetching page token: {str(e)}")
            frappe.log_error(
                title="Page Access Token Network Error",
                message=f"Page ID: {page_id}\nError: {str(e)}\n{frappe.get_traceback()}"
            )
            frappe.throw(_("Network error while fetching page token. Please try again."))
        except Exception as e:
            logger.error(f"Failed to get page access token: {str(e)}")
            frappe.log_error(
                title="Page Access Token Fetch Error",
                message=f"Page ID: {page_id}\nError: {str(e)}\n{frappe.get_traceback()}"
            )
            frappe.throw(_("Failed to get page access token: {0}").format(str(e)))
    
    def _create_ad_on_meta(self):
        """Create ad on Meta platform"""
        try:
            # Validate connection status
            integration = frappe.get_doc("Ads Account Integration", self.ads_account)
            if integration.connection_status != "Connected":
                frappe.throw(_("Ads Account is not connected. Please reconnect the account."))
            
            # Get related documents
            ad_set_doc = frappe.get_doc("Ad Set", self.ad_set)
            if not ad_set_doc.adset_id:
                frappe.throw(_("Ad Set has not been created on Meta yet"))
            
            campaign_doc = frappe.get_doc("Ads Campaign", ad_set_doc.campaign)
            if not campaign_doc.campaign_id:
                frappe.throw(_("Campaign has not been created on Meta yet"))
            
            # Initialize provider
            provider = MetaAdsProvider(self.ads_account)
            
            # Process first creative and media (support for single creative/media for now)
            creative_row = self.ad_creative[0]
            media_row = self.media[0]
            
            # Step 1: Upload media
            # image_hash = self._upload_media(provider, media_row)
            image_url = self._upload_media(provider, media_row)
            
            # Update media row with upload details immediately
            frappe.db.set_value(
                'Ad Media',
                media_row.name,
                {
                    'media_hash': media_row.media_hash,
                    'image_url': media_row.image_url,
                    'uploaded_to_platform': media_row.uploaded_to_platform,
                    'file_size': media_row.file_size
                }
            )
            
            # Step 2: Create creative
            creative_payload, page_access_token = self._build_creative_payload(creative_row, image_url)
            creative_result = provider.create_creative(creative_payload, page_access_token)
            
            if not creative_result.success:
                raise Exception(f"Creative creation failed: {creative_result.error_message}")
            
            creative_id = creative_result.creative_id
            
            # Update creative row with creative_id
            creative_row.creative_id = creative_id
            
            # Save the creative_id immediately to child table
            frappe.db.set_value(
                'Ad Creative',
                creative_row.name,
                'creative_id',
                creative_id
            )
            
            # Step 3: Create ad
            ad_payload = self._build_ad_payload(ad_set_doc, creative_id)
            ad_result = provider.create_ad(ad_payload)
            
            if ad_result.success:
                self.ad_id = ad_result.ad_id  # campaign_id field is used for ad_id
                
                # Save ad_id and status to database immediately
                frappe.db.set_value(
                    'Ad Post',
                    self.name,
                    {
                        'ad_id': self.ad_id,
                        'status': self.status
                    }
                )
                
                # Commit to ensure data is saved
                frappe.db.commit()
                
                frappe.msgprint(
                    _("Ad successfully created on Meta. ID: {0}").format(self.ad_id),
                    indicator="green",
                    alert=True
                )
                
                logger.info(f"✓ Ad created successfully: {self.ad_id}")
            else:
                raise Exception(f"Ad creation failed: {ad_result.error_message}")
        
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Ad creation failed: {error_msg}")
            
            frappe.log_error(
                title="Ad Post - Meta Creation Error",
                message=frappe.get_traceback()
            )
            
            frappe.throw(_("Failed to create ad on Meta: {0}").format(error_msg))
    
    def _upload_media(self, provider, media_row):
        """Upload media file to Meta and return URL"""
        if not media_row.media_file:
            frappe.throw(_("Media file is required"))

        try:
            # Get file document
            file_doc = frappe.get_doc("File", {"file_url": media_row.media_file})
            file_path = file_doc.get_full_path()

            # Validate file exists
            if not os.path.exists(file_path):
                frappe.throw(_("File not found on server: {0}").format(media_row.media_file))

            # Validate file size (10MB limit for images)
            file_size = os.path.getsize(file_path)
            max_size = 10 * 1024 * 1024  # 10MB

            if file_size > max_size:
                frappe.throw(_("File size exceeds 10MB limit"))

            # Prepare upload payload
            upload_payload = {
                "filename": file_path,
                "media_type": media_row.media_type or "Image"
            }

            # Upload to Meta
            result = provider.upload_image(upload_payload)

            if not result.success:
                raise Exception(f"Media upload failed: {result.error_message}")

            # Update media row with upload details - now stores URL instead of hash
            image_url = result.image_url  # campaign_id field contains the image URL
            media_row.image_url = image_url  # Store in image_url field
            media_row.uploaded_to_platform = 1
            media_row.file_size = file_size
            media_row.media_hash = result.image_hash 

            logger.info(f"✅ Media uploaded successfully: {image_url}")

            return image_url  # Return URL instead of hash

        except Exception as e:
            logger.error(f"Media upload failed: {str(e)}")
            frappe.throw(_("Failed to upload media: {0}").format(str(e)))

    def _build_creative_payload(self, creative_row, image_url):
        """Build creative payload for Meta API"""
        # Extract page_id from selected page label
        page_id = self._extract_page_id_from_label(self.select_facebook_page)

        if not page_id:
            frappe.throw(_("Invalid Facebook Page selection"))

        # Validate required fields for creative
        if not creative_row.link_url:
            frappe.throw(_("Link URL is required in Ad Creative"))

        # Get page access token
        page_access_token = self._get_page_access_token(page_id)

        # Build link_data object - only include non-empty fields
        link_data = {
            "link": creative_row.link_url
        }

        # Add message if provided
        if creative_row.body:
            link_data["message"] = creative_row.body

        # Add name/title if provided
        if creative_row.title:
            link_data["name"] = creative_row.title

        # Add description if provided
        if hasattr(creative_row, 'description') and creative_row.description:
            link_data["description"] = creative_row.description

        # Add caption if provided
        if hasattr(creative_row, 'caption') and creative_row.caption:
            link_data["caption"] = creative_row.caption

        # Add call to action if provided
        if creative_row.call_to_action:
            cta_type = creative_row.call_to_action.upper().replace(" ", "_")
            link_data["call_to_action"] = {
                "type": cta_type
            }

        # Add image URL (not hash)
        link_data["picture"] = image_url

        # Build object_story_spec with proper structure
        object_story_spec = {
            "page_id": page_id,
            "link_data": link_data
        }

        # Build final payload
        payload = {
            "name": creative_row.creative_name.strip()[:100],
            "object_story_spec": object_story_spec
        }

        # Log payload for debugging (without sensitive data)
        logger.info(f"Creative payload (page_id: {page_id}, has_page_token: {bool(page_access_token)})")
        logger.debug(f"Payload details: {json.dumps({k: v for k, v in payload.items() if k != 'access_token'}, indent=2)}")

        return payload, page_access_token

    def _build_ad_payload(self, ad_set_doc, creative_id):
        """Build ad payload for Meta API"""
        payload = {
            "name": self.ad_name.strip()[:100],
            "adset_id": ad_set_doc.adset_id,
            "creative": {"creative_id": creative_id},
            "status": self.status
        }
        
        # Add partnership ad settings if enabled
        if self.enable_partnership_ad:
            if self.select_facebook_page:
                payload.setdefault("adlabels", []).append({"name": "Partnership Ad"})
            
            if self.select_instagram_account:
                payload["instagram_handle"] = self.select_instagram_account
        
        return payload
    
    def _update_ad_status(self):
        """Update ad status on Meta"""
        if not self.ad_id:
            return
        
        try:
            provider = MetaAdsProvider(self.ads_account)
            
            # Make API call to update status
            endpoint = f"{self.ad_id}"
            payload = {"status": self.status}
            
            response = provider._make_request("POST", endpoint, json_data=payload)
            
            frappe.msgprint(
                _("Ad status updated to {0}").format(self.status),
                indicator="green",
                alert=True
            )
            
            logger.info(f"✓ Ad status updated: {self.ad_id} -> {self.status}")
        
        except Exception as e:
            logger.error(f"Failed to update ad status: {str(e)}")
            frappe.throw(_("Failed to update ad status on Meta: {0}").format(str(e)))

@frappe.whitelist()
def get_pages_for_account(filters=None):
    """
    Fetch Facebook pages linked to the selected Ads Account Integration
    Returns: List of tuples [(page_id, label), ...]
    """
    # Parse filters if string
    if isinstance(filters, str):
        try:
            filters = json.loads(filters)
        except (json.JSONDecodeError, TypeError):
            filters = {}
    
    account = filters.get("account")
    if not account:
        frappe.msgprint(_("No account selected"), indicator="orange")
        return []
    
    try:
        # Fetch integration document
        integration = frappe.get_doc("Ads Account Integration", account)
        
        # Validate connection status
        if integration.connection_status != "Connected":
            frappe.msgprint(
                _("Account {0} is not connected. Please reconnect the account.").format(account),
                indicator="orange"
            )
            return []
        
        # Get Facebook pages
        pages = integration.get("fb_pages", [])
        
        if not pages:
            frappe.msgprint(
                _("No Facebook pages found for account {0}").format(account),
                indicator="orange"
            )
            return []
        
        # Build result list with proper formatting
        result = []
        for page in pages:
            page_name = (page.page_name or "").strip() or "Unnamed Page"
            page_id = (page.page_id or "").strip()
            
            if not page_id:
                continue
            
            # Format: "Page Name (page_id)"
            label = f"{page_name} ({page_id})"
            result.append([page_id, label])
        
        return result
    
    except frappe.DoesNotExistError:
        frappe.msgprint(
            _("Ads Account Integration {0} not found").format(account),
            indicator="red"
        )
        return []
    
    except frappe.PermissionError:
        frappe.msgprint(
            _("You do not have permission to access this account"),
            indicator="red"
        )
        return []
    
    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Error fetching pages for account {account}"
        )
        frappe.msgprint(
            _("Error fetching pages: {0}").format(str(e)),
            indicator="red"
        )
        return []