---
name: calendar
description: Manage the local macOS Calendar (iCloud) via osascript. Use when the user asks about their schedule, upcoming events, or wants to create/modify calendar events.
---

# Calendar

All operations go through `osascript` (AppleScript) targeting Calendar.app. Events sync via iCloud automatically.

## Available Calendars

Calendar names vary per user. To discover available calendars:

```bash
osascript -e 'tell application "Calendar" to return name of every calendar'
```

Common calendars: Personal, Work, US Holidays, Siri Suggestions

## Get Today's Events

```bash
osascript -e '
set today to current date
set hours of today to 0
set minutes of today to 0
set seconds of today to 0
set tomorrow to today + (1 * days)

tell application "Calendar"
    set output to ""
    repeat with cal in calendars
        set evts to (every event of cal whose start date ≥ today and start date < tomorrow)
        repeat with e in evts
            set output to output & "[" & name of cal & "] " & summary of e & " | " & start date of e & " - " & end date of e & return
        end repeat
    end repeat
    return output
end tell'
```

## Get Events for a Specific Date

Replace the date calculation. Example for tomorrow:

```bash
osascript -e '
set targetDay to (current date) + (1 * days)
set hours of targetDay to 0
set minutes of targetDay to 0
set seconds of targetDay to 0
set nextDay to targetDay + (1 * days)

tell application "Calendar"
    set output to ""
    repeat with cal in calendars
        set evts to (every event of cal whose start date ≥ targetDay and start date < nextDay)
        repeat with e in evts
            set output to output & "[" & name of cal & "] " & summary of e & " | " & start date of e & " - " & end date of e & return
        end repeat
    end repeat
    return output
end tell'
```

## Get This Week's Events

```bash
osascript -e '
set today to current date
set hours of today to 0
set minutes of today to 0
set seconds of today to 0
set endOfWeek to today + (7 * days)

tell application "Calendar"
    set output to ""
    repeat with cal in calendars
        set evts to (every event of cal whose start date ≥ today and start date < endOfWeek)
        repeat with e in evts
            set output to output & "[" & name of cal & "] " & summary of e & " | " & start date of e & " - " & end date of e & return
        end repeat
    end repeat
    return output
end tell'
```

## Create an Event

```bash
osascript -e '
tell application "Calendar"
    tell calendar "Personal"
        set newEvent to make new event with properties {summary:"EVENT_TITLE", start date:date "MONTH DAY, YEAR at HH:MM:SS AM", end date:date "MONTH DAY, YEAR at HH:MM:SS AM"}
    end tell
    save
end tell'
```

Example with location and notes:

```bash
osascript -e '
tell application "Calendar"
    tell calendar "Personal"
        set newEvent to make new event with properties {summary:"Lunch with Alex", start date:date "March 15, 2026 at 12:00:00 PM", end date:date "March 15, 2026 at 1:00:00 PM", location:"Corner Cafe", description:"Catch up re: project"}
    end tell
    save
end tell'
```

## Delete an Event

```bash
osascript -e '
tell application "Calendar"
    tell calendar "CALENDAR_NAME"
        set evts to (every event whose summary is "EVENT_TITLE")
        if (count of evts) = 1 then
            delete item 1 of evts
            save
            return "Deleted"
        else
            return "Found " & (count of evts) & " matches — be more specific"
        end if
    end tell
end tell'
```

## Search Events by Title

```bash
osascript -e '
tell application "Calendar"
    set output to ""
    repeat with cal in calendars
        set evts to (every event of cal whose summary contains "QUERY")
        repeat with e in evts
            set output to output & "[" & name of cal & "] " & summary of e & " | " & start date of e & return
        end repeat
    end repeat
    return output
end tell'
```

## Rules

- Confirm with the user before creating or deleting events
- Default to the "Personal" calendar for new events unless the user specifies otherwise
- Use the user's local timezone for date/time display
- When showing a schedule, sort events chronologically and skip all-day "day type" markers (like "EVEN periods - Day 4") unless asked
