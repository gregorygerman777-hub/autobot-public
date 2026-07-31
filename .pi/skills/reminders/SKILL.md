---
name: reminders
description: Manage macOS Reminders via osascript. Use when the user wants to set reminders, check their reminders, or mark them complete.
---

# Reminders

All operations go through `osascript` targeting Reminders.app. Syncs via iCloud.

## Available Lists

- Reminders (default)

## Create a Reminder

```bash
osascript -e '
tell application "Reminders"
    tell list "Reminders"
        make new reminder with properties {name:"REMINDER_TEXT"}
    end tell
end tell'
```

With a due date:

```bash
osascript -e '
tell application "Reminders"
    tell list "Reminders"
        make new reminder with properties {name:"REMINDER_TEXT", due date:date "MONTH DAY, YEAR at HH:MM:SS AM"}
    end tell
end tell'
```

With a due date and notes:

```bash
osascript -e '
tell application "Reminders"
    tell list "Reminders"
        make new reminder with properties {name:"REMINDER_TEXT", due date:date "March 15, 2026 at 9:00:00 AM", body:"Additional notes here"}
    end tell
end tell'
```

## List Incomplete Reminders

```bash
osascript -e '
tell application "Reminders"
    set output to ""
    repeat with l in lists
        set incompleteReminders to (every reminder of l whose completed is false)
        repeat with r in incompleteReminders
            set output to output & "[" & name of l & "] " & name of r
            try
                set d to due date of r
                set output to output & " | due: " & d
            end try
            set output to output & return
        end repeat
    end repeat
    return output
end tell'
```

## Complete a Reminder

```bash
osascript -e '
tell application "Reminders"
    set matches to (every reminder whose name contains "QUERY" and completed is false)
    if (count of matches) = 1 then
        set completed of item 1 of matches to true
        return "Completed"
    else
        return "Found " & (count of matches) & " matches — be more specific"
    end if
end tell'
```

## Delete a Reminder

```bash
osascript -e '
tell application "Reminders"
    set matches to (every reminder whose name contains "QUERY")
    if (count of matches) = 1 then
        delete item 1 of matches
        return "Deleted"
    else
        return "Found " & (count of matches) & " matches — be more specific"
    end if
end tell'
```

## Rules

- Default to "Reminders" list unless user specifies otherwise
- When user says "remind me to X at Y", create with a due date
- When user says "remind me to X", create without a due date
- Confirm before deleting reminders
