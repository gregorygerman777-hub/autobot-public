---
name: contacts
description: Manage macOS Contacts via osascript. Use when the user wants to add, search, update, or delete contacts, or look up who a phone number belongs to.
---

# Manage Contacts

All operations go through `osascript` (AppleScript) so changes sync via iCloud automatically.

## Add a Contact

```bash
osascript -e '
tell application "Contacts"
    set newPerson to make new person with properties {first name:"FIRST", last name:"LAST"}
    make new phone at end of phones of newPerson with properties {label:"mobile", value:"+1XXXXXXXXXX"}
    save
end tell'
```

To also add an email:
```bash
osascript -e '
tell application "Contacts"
    set newPerson to make new person with properties {first name:"FIRST", last name:"LAST"}
    make new phone at end of phones of newPerson with properties {label:"mobile", value:"+1XXXXXXXXXX"}
    make new email at end of emails of newPerson with properties {label:"home", value:"user@example.com"}
    save
end tell'
```

## Search for a Contact

```bash
osascript -e '
tell application "Contacts"
    set matches to every person whose name contains "QUERY"
    set output to ""
    repeat with p in matches
        set output to output & name of p & " | "
        try
            set output to output & value of first phone of p
        end try
        set output to output & return
    end repeat
    return output
end tell'
```

## Get Full Contact Details

```bash
osascript -e '
tell application "Contacts"
    set matches to every person whose name contains "QUERY"
    set output to ""
    repeat with p in matches
        set output to output & "Name: " & name of p & return
        repeat with ph in phones of p
            set output to output & "Phone (" & label of ph & "): " & value of ph & return
        end repeat
        repeat with em in emails of p
            set output to output & "Email (" & label of em & "): " & value of em & return
        end repeat
        try
            set output to output & "Org: " & organization of p & return
        end try
        set output to output & "---" & return
    end repeat
    return output
end tell'
```

## Update a Contact (add a phone/email to existing)

```bash
osascript -e '
tell application "Contacts"
    set matches to every person whose name contains "QUERY"
    if (count of matches) = 1 then
        set p to item 1 of matches
        make new phone at end of phones of p with properties {label:"work", value:"+1XXXXXXXXXX"}
        save
    else
        return "Found " & (count of matches) & " matches — be more specific"
    end if
end tell'
```

## Delete a Contact

```bash
osascript -e '
tell application "Contacts"
    set matches to every person whose name contains "QUERY"
    if (count of matches) = 1 then
        delete item 1 of matches
        save
        return "Deleted"
    else
        return "Found " & (count of matches) & " matches — be more specific"
    end if
end tell'
```

## Reverse Lookup (phone number to name)

```bash
osascript -e '
tell application "Contacts"
    set matches to every person whose value of phones contains "+1XXXXXXXXXX"
    set output to ""
    repeat with p in matches
        set output to output & name of p & return
    end repeat
    if output = "" then return "No contact found for this number"
    return output
end tell'
```

## Rules

- Always confirm with the user before deleting a contact
- When updating, verify match is unique (count = 1) before modifying
- Phone numbers should be in E.164 format (+1XXXXXXXXXX)
- Use `save` after every mutation
