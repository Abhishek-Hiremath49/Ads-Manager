# Copyright (c) 2026, Abhishek and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class AdMedia(Document):
    def validate(self):
        if self.media_file and not self.media_type:
            self.media_type = "Image" if self.media_file.lower().endswith(('.jpg', '.png')) else "Video"