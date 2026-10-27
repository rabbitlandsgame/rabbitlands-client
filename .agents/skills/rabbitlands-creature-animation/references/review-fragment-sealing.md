# Review fragments and sealed delivery revisions

Generated review pages can be valid HTML fragments without explicit body or html closing tags. When adding contact or ending-pose links, handle both complete documents and fragments. Assert that the section is present in the actual actor review and that every local target exists before sealing its manifest. A replace call that changes nothing must fail the check.

A failed prerequisite must stop the subsequent sealing command. Prefer one Python controller with checked subprocess calls, or explicit shell exit-code handling. A PowerShell session can otherwise continue after a Python assertion and seal a page that failed its link check.

If a link defect is found after sealing, preserve the sealed delivery and frozen provenance. Create a new UI revision, retain byte-identical motion/media and qualifications, record the base and patch hashes, and verify the corrected links. Native motion does not need to be regenerated for an HTML-only fix. Update the review selection while preserving the prior version and all human feedback. Keep native recipe and UI recipe identities explicit.

Bind sealing, catalog refresh and comment storage to the literal owned task worktree and validate that root. Read-only archive paths are evidence/media inputs, never output roots. Check that catalog refresh writes only task-local state; confirm historical stores and unrelated review versions remain unchanged. A local HTTP range check confirms seekable media delivery but does not claim browser playback or human approval.
