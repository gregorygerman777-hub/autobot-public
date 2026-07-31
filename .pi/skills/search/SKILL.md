---
name: search
description: Search for files, documents, and content on the local Mac using Spotlight (mdfind). Use when the user asks to find a file, PDF, download, document, or anything on their computer.
---

# Search (Spotlight)

Uses `mdfind` (Spotlight CLI) to find files on the local Mac.

## Find Files by Name

```bash
mdfind -name "filename"
```

## Find Files by Content

```bash
mdfind "search query"
```

## Find Files by Type

```bash
# PDFs
mdfind "kMDItemContentType == 'com.adobe.pdf'"

# Images
mdfind "kMDItemContentType == 'public.image'"

# Word docs
mdfind "kMDItemContentType == 'org.openxmlformats.wordprocessingml.document'"

# Any file type by extension
mdfind "kMDItemFSName == '*.xlsx'"
```

## Combined Queries

```bash
# PDFs containing "machine learning"
mdfind "kMDItemContentType == 'com.adobe.pdf' && kMDItemTextContent == '*machine learning*'"

# Files modified today
mdfind "kMDItemFSContentChangeDate >= \$time.today"

# Files modified in the last 7 days
mdfind "kMDItemFSContentChangeDate >= \$time.this_week"

# Downloads folder only
mdfind -onlyin ~/Downloads "query"

# Projects folder only
mdfind -onlyin ~/Projects "query"
```

## Find Recent Downloads

```bash
# Recent PDFs in Downloads
mdfind -onlyin ~/Downloads "kMDItemContentType == 'com.adobe.pdf'" | head -10

# Anything downloaded recently
mdfind -onlyin ~/Downloads "kMDItemFSContentChangeDate >= \$time.this_week"
```

## Get File Info

```bash
# Full metadata for a file
mdls "/path/to/file"

# Specific attribute
mdls -name kMDItemContentType "/path/to/file"
```

## Rules

- Use `-onlyin` to scope searches when the user mentions a specific location
- Limit results with `| head -N` for broad queries
- Use `-name` for filename searches, plain query for content searches
- When user says "that PDF" or "the file I downloaded", search Downloads first
- Show full paths in results so the user can open them
