# Starship launch calendar

Auto-updating iCalendar feed of SpaceX Starship flights, rebuilt every hour by GitHub Actions
from [Launch Library 2](https://thespacedevs.com/llapi) by The Space Devs.

**Subscribe URL:** `https://raw.githubusercontent.com/leodesca01/starship-calendar/main/docs/starship.ics`

- Delays and scrubs move the existing event (stable UID per launch).
- Cancelled flights disappear on the next refresh.
- Times are UTC in the feed; your calendar shows them in local time.
- Exact T-0: timed event with alerts at T-1h and T-10min.
- Only a rough NET (day, week, month): all-day placeholder tagged `[NET ...]`.
- The last few flights stay in the calendar with their outcome.

Manual refresh: Actions → "Update Starship calendar" → Run workflow.
