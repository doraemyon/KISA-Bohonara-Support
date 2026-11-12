# Notice translation review

Compare the two English versions against the same Korean source. The baseline
is the archived translation, using the original automatic draft for 72230.
Apply the same 17 meaning checks to both outputs. A missing or ambiguous
requirement fails its check. Report missing Gemini output separately.

| Notice | Checks | Baseline pass count |
| --- | --- | --- |
| 72132 | General notice summary. Repository history may retain the exposed credentials after deletion and the credentials must be revoked or rotated. MFA on key systems. Avoid standing administrator-level access keys. | 3 / 4 |
| 72230 | Isolate the host without rebooting before evidence collection. Rotate the credentials of compromised hosts. PHP 8.1 and earlier includes 8.1 itself. PHP 8.2 support ends on 2026-12-31 and migration to 8.3 or later is recommended. Redeploy container deployments with updated images. | 1 / 5 |
| 72284 | Version 7.0 is within the affected range. Pause self-registration and use manual registration. Allow only approved upload extensions. | 3 / 3 |
| 72302 | The 24.22.0–24.22.3 affected interval includes the lower version and excludes the upper version. The 22.22.3-or-earlier affected range includes 22.22.3. The 26.3.1 fixed range includes 26.3.1 and later versions. | 3 / 3 |
| 72295 | The four affected SAP products are mapped to the appropriate CVEs. Their separate patch references match the source rows. | 2 / 2 |

The comparison also applies the production format validator independently.
Archived publication and the time it took to obtain a new model response are
not directly comparable. This sample does not estimate a production failure rate.
