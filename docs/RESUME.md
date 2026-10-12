# Resume editing

The Resume navigation section replaces the general Notes screen. Existing project notes and decisions remain available inside project workspaces and are not deleted.

Choose Upload resume to store an encrypted account copy, edit it across devices, and download the updated Word file. Cloud edits do not change the original PC file. Alternatively, choose Link local file and enter the original `.docx` path on the service computer. This grants access to that exact file; it does not approve the whole Desktop folder or grant AI access.

Click a paragraph to edit its text, then choose Save to computer. TgTop updates the original Word file while retaining its existing paragraph/run formatting and other document parts. The editor shows editable text with basic bold/italic cues, rather than an exact Word page-layout preview. Word fields must be edited in Word. Use Word for inserting sections, changing layout, tables, images, headers, or advanced formatting. Paragraph editing does not insert new paragraphs.

TgTop checks the file revision before saving. If Word or another process changed it since loading, reload the file and review your changes. If Word locks the file, close Word and try saving again. Automatic refresh pauses on this screen, and navigation asks before discarding unsaved edits.

Before each save, TgTop retains one encrypted recovery copy in private application storage. Restore previous save requires confirmation and checks the current revision. This provides one previous version, not a full version history. Managed application backups include the encrypted recovery blob, but the external Word file itself is not copied into ordinary application backups. Keep your normal computer/document backups as well.

The linked computer must be awake and accessible to its service. A hosted service cannot directly edit a Word file on an offline Windows PC. Resume contents are excluded from AI access, general search, activity logs, and SMS. The authenticated owner sees the linked path and document text; decryption of the recovery copy occurs only within the service during restoration.
