# Copyright (c) 2026, Abhishek and contributors
# For license information, please see license.txt

import frappe
import logging
import json
from frappe import _
from frappe.model.document import Document
from ads_manager.ads_manager.providers.meta_ads import MetaAdsProvider

logger = logging.getLogger(__name__)


class AdPost(Document):
    """
    Ad Post Document
    Creates and posts ads to Meta platforms (Facebook/Instagram)
    Automatically creates ad creative and posts to Facebook
    """

    def before_save(self):
        """Create ad creative and post to Facebook before saving"""
        # Update status based on enable checkbox
        self.status = "ACTIVE" if self.enable else "PAUSED"
        
        # Only create ad if this is new or ad_id is empty
        if self.is_new() or not self.ad_id:
            self._create_and_post_ad()

    def _create_and_post_ad(self):
        """
        Create ad creative and post to Facebook
        This is the main orchestration method
        """
        try:
            # Validate required fields
            self._validate_required_fields()

            # Get ad set document to fetch account and campaign details
            ad_set_doc = frappe.get_doc("Ad Set", self.ad_set)
            campaign_doc = frappe.get_doc("Ads Campaign", ad_set_doc.campaign)
            
            if not campaign_doc.account:
                frappe.throw(_("Selected campaign has no associated account"))

            # Initialize provider with the account
            provider = MetaAdsProvider(campaign_doc.account)

            # Step 1: Create ad creative from media
            logger.info(f"Step 1: Creating ad creative for '{self.ad_name}'")
            creative_id = self._create_ad_creative(provider, campaign_doc)

            # Step 2: Post ad to Facebook
            logger.info(f"Step 2: Posting ad to Facebook")
            ad_payload = self._build_ad_payload(ad_set_doc, creative_id)
            result = provider.create_ad(ad_payload)

            if result.success:
                # Store the ad_id returned from Meta
                self.ad_id = result.campaign_id
                # Update the document with ad_id
                frappe.db.set_value(self.doctype, self.name, "ad_id", self.ad_id)
                logger.info(f"✓ Ad posted successfully to Meta: {result.campaign_id}")
                frappe.msgprint(
                    _("Ad posted successfully to Meta Ads. ID: {0}").format(result.campaign_id),
                    alert=True,
                )
            else:
                error_msg = result.error_message or "Unknown error from Meta API"
                logger.error(f"Failed to post ad to Meta: {error_msg}")
                frappe.throw(_("Failed to post ad to Meta Ads: {0}").format(error_msg))

        except frappe.ValidationError:
            # Re-raise validation errors
            raise
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Unexpected error creating and posting ad: {error_msg}")
            frappe.log_error(frappe.get_traceback(), "Ad Post Creation Error")
            frappe.throw(_("Failed to create and post ad: {0}").format(error_msg))

    def _validate_required_fields(self):
        """Validate all required fields"""
        if not self.ad_name:
            frappe.throw(_("Ad Name is required"))
        if not self.ad_set:
            frappe.throw(_("Ad Set is required"))
        if not self.ads_account:
            frappe.throw(_("Ads Account is required"))
        if not self.media or len(self.media) == 0:
            frappe.throw(_("At least one media file is required"))
        
        # Check if media has at least one file
        media_with_files = [row for row in self.media if row.media_file]
        if not media_with_files:
            frappe.throw(_("At least one media file is required in the media section"))

    def _create_ad_creative(self, provider, campaign_doc) -> str:
        """
        Create ad creative from media and return creative_id
        """
        try:
            # Upload media files and get hashes
            image_hash = None
            for media_item in self.media:
                if media_item.media_file:
                    media_hash = self._upload_media(provider, media_item)
                    # Use first image as primary
                    if not image_hash and media_item.media_type in ["Image", None]:
                        image_hash = media_hash

            if not image_hash:
                frappe.throw(_("At least one image file is required"))

            # Build creative payload
            creative_payload = self._build_creative_payload(image_hash, campaign_doc)

            logger.info(f"Creating creative with payload: {creative_payload}")

            # Create creative on Meta
            result = provider.create_creative(creative_payload)

            if result.success:
                logger.info(f"✓ Creative created successfully: {result.creative_id}")
                return result.creative_id
            else:
                error_msg = result.error_message or "Unknown error"
                logger.error(f"Failed to create creative: {error_msg}")
                frappe.throw(_("Failed to create ad creative: {0}").format(error_msg))

        except Exception as e:
            logger.error(f"Error creating creative: {str(e)}")
            frappe.log_error(frappe.get_traceback(), "Ad Creative Creation Error")
            raise

    def _build_creative_payload(self, image_hash: str, campaign_doc) -> dict:
        """Build creative payload for Meta API"""
        # Get page_id from ads_account
        account_doc = frappe.get_doc("Ads Account Integration", self.ads_account)
        
        # Get first page as default - in production, this could be user-selectable
        pages = account_doc.get("fb_pages", [])
        if not pages:
            frappe.throw(_("No Facebook pages found in the selected account"))
        
        page_id = pages[0].page_id if pages else None
        if not page_id:
            frappe.throw(_("No valid page ID found"))

        # Build link data
        link_data = {
            "image_hash": image_hash,
        }

        # Add optional fields from the ad post
        if self.ad_name:
            link_data["message"] = self.ad_name

        object_story_spec = {
            "page_id": page_id,
            "link_data": link_data,
        }

        payload = {
            "name": self.ad_name.strip()[:100],
            "object_story_spec": json.dumps(object_story_spec),
        }

        return payload

    def _build_ad_payload(self, ad_set_doc, creative_id: str) -> dict:
        """
        Build ad payload with all mappings and validations
        All validation and mapping happens here before sending to Meta API
        """
        if not ad_set_doc.adset_id:
            frappe.throw(_("Ad Set has no Meta ad set ID"))
        
        if not creative_id:
            frappe.throw(_("Creative ID is required"))

        payload = {
            "name": self.ad_name.strip()[:100],
            "adset_id": ad_set_doc.adset_id,
            "creative": {"creative_id": creative_id},
            "status": "PAUSED",  # Start in paused state for safety
        }
        
        # Add partnership ad fields if enabled
        if self.enable_partnership_ad:
            if self.select_facebook_page:
                payload["adlabels"] = [{"name": "Partnership Ad"}]
            if self.select_instagram_account:
                payload["instagram_handle"] = self.select_instagram_account

        return payload

    def _upload_media(self, provider, media_item) -> str:
        """
        Upload media file to Meta and return media hash
        """
        import os

        if not media_item.media_file:
            frappe.throw(_("Media file is required"))

        try:
            # Get file document
            file_doc = frappe.get_doc("File", {"file_url": media_item.media_file})

            # Get the full file path
            file_path = file_doc.get_full_path()

            if not os.path.exists(file_path):
                frappe.throw(_("Media file not found at {0}").format(file_path))

            # Get file size for logging
            file_size = os.path.getsize(file_path)
            logger.info(f"Uploading media file: {file_path} (size: {file_size} bytes)")

            # Upload payload
            upload_payload = {
                "filename": file_path,
                "media_type": media_item.media_type or "Image",
            }

            image_result = provider.upload_image(upload_payload)
            if not image_result.success:
                frappe.throw(_("Media upload failed: {0}").format(image_result.error_message))

            logger.info(f"✓ Media uploaded successfully, hash: {image_result.campaign_id}")
            return image_result.campaign_id

        except frappe.DoesNotExistError:
            frappe.throw(_("Media file document not found"))
        except Exception as e:
            logger.error(f"Error uploading media: {str(e)}")
            frappe.log_error(frappe.get_traceback(), "Media Upload Error")
            frappe.throw(_("Error uploading media: {0}").format(str(e)))
