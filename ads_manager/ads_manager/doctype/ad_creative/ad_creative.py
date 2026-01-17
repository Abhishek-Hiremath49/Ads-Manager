# Updated ad_creative.py with creation logic

# Copyright (c) 2026, Abhishek and contributors
# For license information, please see license.txt

import frappe
import logging
import json
from frappe import _
from frappe.model.document import Document
from ads_manager.ads_manager.providers.meta_ads import MetaAdsProvider

logger = logging.getLogger(__name__)


class AdCreative(Document):
    """
    Ad Creative Document
    Creates and manages ad creatives on Meta platforms (Facebook/Instagram)
    """

    def before_save(self):
        """Validate media before creating creative"""
        # Check if media has at least one file
        media_with_files = [row for row in self.media if row.media_file]
        if not media_with_files:
            frappe.throw(_("At least one media file is required"))

        # Try to create creative on Meta Ads before saving
        # Only create creative if this is new or creative_id is empty
        if (self.is_new() or not self.creative_id) and self.link:
            # Only attempt Meta creation if link is provided
            try:
                self._create_meta_creative()
            except Exception as e:
                # Log the error but continue - allow user to save locally even if Meta fails
                logger.error(f"Meta creative creation failed: {str(e)}")
                frappe.msgprint(
                    _(
                        "Warning: Creative creation on Meta failed. The ad creative has been saved locally. Error: {0}"
                    ).format(str(e)),
                    indicator="orange",
                )
        elif not self.link:
            # No link provided - just save locally without Meta creation
            logger.info("No link provided - skipping Meta creative creation")

    def validate(self):
        """Validate required fields"""
        if not self.account:
            frappe.throw(_("Account is required to create a creative"))
        if not self.name1:
            frappe.throw(_("Creative Name is required"))
        if not self.page:
            frappe.throw(_("Page is required"))

        # Check for media files - ensure media exists before checking
        if not self.media:
            frappe.throw(_("At least one media file is required"))

        media_with_files = [row for row in self.media if row.get("media_file")]
        if not media_with_files:
            frappe.throw(_("At least one media file is required"))

    def _create_meta_creative(self):
        """
        Create creative via Meta Ads provider and store the creative_id

        Raises:
            frappe.ValidationError: If required fields are missing or API call fails
        """
        # Validate required fields
        if not self.account:
            frappe.throw(_("Account is required to create a creative"))
        if not self.name1:
            frappe.throw(_("Creative Name is required"))
        if not self.page:
            frappe.throw(_("Page is required"))
        if not self.media or len(self.media) == 0:
            frappe.throw(_("At least one media file is required"))

        try:
            # Initialize provider with the account integration
            provider = MetaAdsProvider(self.account)

            # Upload media files and get hashes
            image_hash = None
            for media_item in self.media:
                if media_item.media_file:
                    media_hash = self._upload_media(provider, media_item)
                    # Use first image as primary for now
                    if not image_hash and media_item.media_type == "Image":
                        image_hash = media_hash

            if not image_hash:
                frappe.throw(_("At least one image file is required"))

            # Extract page_id from page field (may contain full label like "Page Name (ID)")
            page_id = self.page
            if "(" in page_id and ")" in page_id:
                # Extract ID from label format "Page Name (ID)"
                page_id = page_id.split("(")[-1].rstrip(")")

            # Prepare minimal payload for Meta API
            # Start with basic structure that Meta accepts
            link_data = {
                "image_hash": image_hash,
            }

            # Add optional fields only if they have values
            if self.message:
                link_data["message"] = self.message
            if self.link:
                link_data["link"] = self.link
            if self.caption:
                link_data["caption"] = self.caption
            if self.description:
                link_data["description"] = self.description

            # Only add call_to_action if link is provided and CTA is specified
            if self.link and self.call_to_action:
                link_data["call_to_action"] = {
                    "type": self.call_to_action.upper().replace(" ", "_"),
                    "value": {"link": self.link},
                }

            object_story_spec = {
                "page_id": page_id,
                "link_data": link_data,
            }

            payload = {
                "name": self.name1,
                "object_story_spec": json.dumps(object_story_spec),  # Convert to JSON string for Meta API
            }

            logger.info(f"Creating creative '{self.name1}' on Meta Ads with payload: {payload}")

            # Create creative on Meta
            result = provider.create_creative(payload)

            if result.success:
                # Store the creative_id returned from Meta
                self.creative_id = result.creative_id
                logger.info(f"✓ Creative created successfully on Meta: {result.creative_id}")
                frappe.msgprint(
                    _("Creative created successfully on Meta Ads. ID: {0}").format(result.creative_id),
                    alert=True,
                )
            else:
                error_msg = result.error_message or "Unknown error from Meta API"
                logger.error(f"Failed to create creative on Meta: {error_msg}")
                # Re-raise the error to be caught by before_save wrapper
                raise ValueError(error_msg)

        except frappe.DoesNotExistError:
            frappe.throw(_("Account '{0}' does not exist.").format(self.account))
        except ValueError as e:
            frappe.throw(_("Invalid configuration: {0}").format(str(e)))
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Unexpected error creating creative: {error_msg}")
            frappe.log_error(frappe.get_traceback(), "Ad Creative Creation Error")
            frappe.throw(_("Failed to create creative: {0}").format(error_msg))

    def _upload_media(self, provider, media_item):
        """Upload media file to Meta and update the media_item with hash"""
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

            # Get file size
            file_size = os.path.getsize(file_path)

            # Meta upload payload with full file path
            # The provider expects the full path so it can open the file
            upload_payload = {
                "filename": file_path,  # Pass full path, not just basename
                "media_type": media_item.media_type or "Image",
            }

            image_result = provider.upload_image(upload_payload)
            if not image_result.success:
                frappe.throw(_("Media upload failed: {0}").format(image_result.error_message))

            # Update media item with hash and metadata
            # Note: image_hash is stored in campaign_id field of PublishResult
            media_item.media_hash = image_result.campaign_id
            media_item.file_size = file_size
            media_item.uploaded_to_platform = 1

            return image_result.campaign_id

        except frappe.DoesNotExistError:
            frappe.throw(_("Media file document not found"))
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Media Upload Error")
            frappe.throw(_("Error uploading media: {0}").format(str(e)))


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_pages_for_account(doctype, txt, searchfield, start, page_len, filters):
    """Fetch pages linked to an ads account"""
    # Handle filters - could be dict or string
    if isinstance(filters, str):
        import json

        try:
            filters = json.loads(filters)
        except:
            filters = {}

    account = filters.get("account") if isinstance(filters, dict) else None

    if not account:
        return []

    try:
        integration = frappe.get_doc("Ads Account Integration", account)
    except frappe.DoesNotExistError:
        logger.warning(f"Account '{account}' not found")
        return []

    # Get pages from integration's fb_pages child table
    pages = integration.get("fb_pages", [])

    if not pages:
        logger.info(f"No pages found for account '{account}'")
        return []

    result = []
    txt = (txt or "").lower()

    for page in pages:
        page_id = page.get("page_id") if isinstance(page, dict) else getattr(page, "page_id", None)
        page_name = page.get("page_name") if isinstance(page, dict) else getattr(page, "page_name", "Unnamed")
        page_name = page_name or "Unnamed"

        if not page_id:
            continue

        label = f"{page_name} ({page_id})"

        if not txt or txt in label.lower():
            result.append([page_id, label])

    return result
