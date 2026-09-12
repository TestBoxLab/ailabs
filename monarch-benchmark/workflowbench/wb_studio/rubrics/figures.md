# Figures and layout — the Swiss technical manual, in rules

From `docs/AI-LABS-STUDIO-DESIGN-SYSTEM-2026-09-09.md` and the audit of 10 September. Cite a
finding as `figures:<id>`. Numbers under F10 to F13 come from the measured layout record, not from
looking at the picture.

## F1 One signal colour
Red marks the current place, and nothing else. A second accent anywhere on a page is a defect.

## F2 Meaning colours stay in results
Green for passed, red for failed, one hue per model family — only in results and figures. Never in
navigation, headings or chrome.

## F3 Rules, not boxes
Separation is a hairline rule or whitespace. A card with a border and a shadow around ordinary
content is a defect.

## F4 Booktabs tables
A rule above the header, a rule below the header, a rule at the end. No vertical rules, no zebra
striping, no cell borders.

## F5 A label column
Facts read as label on the left, value on the right, aligned down the page. Not a paragraph with
the value buried in it.

## F6 Every figure carries its source line
A chart or a table names the run, the task set and the date it was computed from. A figure without
one is not publishable.

## F7 Numbers in the mono face, sentences in the text face
A measured value in a proportional face, or a sentence in the mono face, is a defect.

## F8 Numbered sections in a report
A report's sections are numbered so a reader can cite one.

## F9 No decoration that carries no information
No icon that repeats the word beside it, no illustration, no gradient, no rounded pill around a
word that is already a heading.

## F10 No horizontal overflow
`overflow_px` is 0 at 1440 wide. Anything above it is a defect.

## F11 Nothing is clipped
An element whose content is wider than its box, with overflow hidden, is cutting text off.

## F12 Contrast
Body text at 4.5:1 or better; text at 18.66px or above, or 14px bold and above, at 3:1 or better.
The lowest ratios in the measured record are the ones to read.

## F13 Nothing below 11px
The smallest text in the measured record is 11px or larger.

## F14 Heading order
h1 then h2 then h3, with no level skipped, and one h1 per page.

## F15 A table that scrolls sideways has said so
A table wider than its container either fits, wraps or is visibly scrollable. Silent clipping is a
defect.
