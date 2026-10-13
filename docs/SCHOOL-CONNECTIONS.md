# School connections

Open Connections & devices → School connections. Select a destination project for each service. New deadlines wait for review before becoming calendar tasks. Approved tasks refresh every 15 minutes on the backend, including while the PC is off. A failed refresh shows an error and the last successful check. Existing tasks remain intact.

## Canvas

Choose an access token for richer assignment data, or a private iCalendar feed for calendar events and assignments. The API uses the student planner endpoint. Token creation lives under Canvas Account → Settings and may be disabled by the school. This release supports public HTTPS `*.instructure.com` sites. Private calendar feed URLs act as credentials and never appear in ordinary state responses or AI context.

Feed limitations: Canvas excludes To Do items and limits its feed window/item count. TgTop rejects recurring ICS events rather than silently dropping repeated occurrences. Use the API or an expanded CSV/ICS schedule for those events. Canvas API pagination stops at 1,000 items with a clear failure instead of importing a partial result.

## Outlook

Choose Microsoft sign-in for the primary Outlook calendar, or a published Outlook HTTPS ICS calendar. Microsoft sign-in needs an Entra app registration supporting the intended Microsoft account type, a client ID, and a client secret entered privately in TgTop. Register the Web redirect URI shown in setup, ending `/school/outlook/callback`. Request delegated `Calendars.Read`; MSAL adds authentication and refresh scopes. School policy may require administrator consent. No Microsoft mail access or calendar write permission is requested.

The app uses MSAL's authorization-code flow with state and PKCE. Its encrypted account configuration holds the token cache and application secret. Authorization expires after ten minutes, requires a still-valid originating TgTop session, and cannot be replayed. Reconnect when Microsoft revokes authorization or the application secret expires. The calendar window covers the next 180 days; recurring occurrences come from Microsoft's expanded calendarView endpoint.

## Gradescope

Gradescope has no public student API. This release does not offer direct Gradescope authentication, scrape logged-in pages, or store a Gradescope password.

Choose Canvas-linked assignments after connecting Canvas through its API. TgTop reads active Canvas courses and assignments whose external-tool URL belongs to Gradescope, using Canvas's published due date. Items absent from Canvas, unpublished deadlines, institution-specific opaque LTI URLs, and Gradescope-only extensions may not appear. Check the Gradescope assignment page for the authoritative deadline. This adapter supports up to 20 active courses and 100 assignments per course and fails clearly if limits would truncate results.

Alternatively upload a manually prepared CSV or ICS schedule. CSV requires `title` and `due_at` columns. Optional `source_id` should identify an assignment permanently; optional `url` links to its source. Use an ISO date/time with offset, for example `2026-11-03T18:00:00-05:00`. Without a source ID, the title identifies the item, so renaming it creates a new review item. No native Gradescope CSV export is assumed. Manual upload is a snapshot, not automatic syncing.

## Review, changes, and privacy

Import each proposed deadline with Add to my calendar. Existing imported tasks retain completion state. If you edited the task's title, project or due date locally, a source change enters conflict review rather than overwriting your edit. Explicitly accepting a conflict replaces those three fields only. Locally deleted tasks stay deleted. Missing source items show a review notice and never delete a task because feeds can use limited date windows.

Canvas-linked Gradescope assignments share a stable source identity with the Canvas adapter, preventing a second task for the same assignment. Source IDs distinguish assignments within an encrypted user store; different TgTop users never share connector configuration. A repeated unchanged refresh creates no new deadline events.

Credentials and private feed URLs stay in encrypted service configuration, outside AI tools, ordinary export records and notifications. Imported task titles and source links become normal project data and can enter authorized AI context if you enable that project's AI access. Disconnect removes active connector credentials without removing tasks; revoke the provider grant separately in Microsoft/Canvas settings if needed. Encrypted backups include connection configuration and must remain private.

Connector code and mock transport tests can run without external credentials. Live account access requires your provider setup and authorization. No provider data is simulated as live syncing.

References: [Canvas planner](https://canvas.instructure.com/doc/api/planner.html), [Canvas calendar feeds](https://community.instructure.com/en/kb/articles/662804-how-do-i-view-the-calendar-ical-feed-to-subscribe-to-an-external-calendar), [Microsoft calendarView](https://learn.microsoft.com/en-us/graph/api/calendar-list-calendarview?view=graph-rest-1.0), [MSAL authorization flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow), [Gradescope public API status](https://guides.gradescope.com/hc/en-us/articles/36028522325901-Gradescope-Public-API).
