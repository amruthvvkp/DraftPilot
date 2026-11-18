# Journey map

The Journey map (**Journey map** in the project's tools, next to the stepper's Characters) lays your
characters' timelines side by side. Each character gets a lane, and each card is one moment in that
character's journey: its title, its story time, what they want (objective) and how they feel
(emotional state). A coloured band on the card's edge shows its **intensity**, from −5 (a low) to
+5 (a high).

It reads the same cards as each character's timeline on the **Characters** page. Add or edit a card
in either place.

## Two axes

The map separates two orders that differ whenever you use a flashback, a cold open or intercutting:

| Axis | Columns are | Dragging a card |
|---|---|---|
| **Narrative** (the default) | acts, then their scenes in script order, then beats that have no scene | proposes a scene reorder, or moves a beat |
| **Chronology** | the story-world order, labelled by each card's story time | changes when the moment happens |

Switch with the **Narrative / Chronology** buttons at the top.

## Cards

- **Add card** in a lane's header adds a card for that character and opens it.
- Click a card's title to open it in the side panel. There you can edit its title, story time,
  **story order** (a number that places it on the Chronology axis; leave it blank for undated),
  objective, motivation, emotional state, intensity, history and description, and link it to a
  scene or a beat. **Save card** saves it at once (this is a direct edit, not a proposal). If
  someone else changed the card meanwhile, the map says so and loads the latest version.
- **Unplaced** holds cards with no place on the current axis: on Narrative, cards linked to no scene
  or beat; on Chronology, cards with no story order. On Narrative, drag a card by its handle onto a
  scene in the script strip, or pick its scene in the panel. On Chronology, **Place on axis** puts it
  at the end of story time.

## Shared moments

A shared moment is one moment several characters are in, such as a meeting or a confrontation. The
map draws it once, across the lanes of everyone in it, with each character's own objective and
feelings at their lane.

The map never merges cards for you. To create one:

1. Tick the small box on each card you want to merge (from at least two characters), or click
   **Select them** where the map notices cards that share a scene or beat.
2. Click **Merge into a shared moment**.

Open the moment to edit what happens and when, or click a character's name on it to edit their side.
**Leave shared moment** (on a character's card) takes them out; **Dissolve moment** removes the
moment and leaves everyone's cards in place.

## Reordering the story

On the Narrative axis, the **script strip** above the map is the script itself: scene numbers,
headings and estimated runtimes. Hover or focus a scene to highlight its cards.

Moving a scene never changes the script straight away. It creates a **reorder proposal**:

1. Drag a scene in the strip (or a card on the map) earlier or later. The map shows the new order,
   with moved scenes and their cards drawn as dashed ghosts and their old numbers.
2. **Apply reorder** changes the script. **Discard** drops the proposal.
3. After applying, **Roll back** restores the previous order.

A scene stays in its act. To move a scene to another act, use the Outline. Cards placed by a beat
that has no scene move the beat instead (as on the Outline page): earlier, later, or to the previous
or next act.

To try several orders, type a name and click **Save as variant**. This stores the order on screen
(the proposal's, if there is one) without applying it. Pick a variant and click **Propose variant**
to turn it back into a proposal you can apply. Scenes added since you saved it go at the end.

The timeline board (**Timeline** in the script editor) still works and uses the same proposals.

## Curves, cast and relationships

- **Intensity curves** draws a line of intensity through each lane, so flat runs and missing lows
  stand out.
- **Cast overlay** adds a band under the lanes with the average of every lane's intensity.
- **Relationships** draws the relationships from the Characters page between the lanes, such as
  "father of" or "rival".

**Lanes** on the left sets the lanes' order, which is the cast's order across the project. Drag a
name or use its arrows.

## Keyboard

Every drag has a keyboard equivalent:

| To | Do this |
|---|---|
| Move a card (or its scene) earlier or later | Focus the card's title and press **Alt + ←** or **Alt + →**, or use **Earlier** / **Later** in its panel |
| Move a beat card to the previous or next act | **Alt + ↑** / **Alt + ↓**, or **Previous act** / **Next act** in its panel |
| Move a scene in the strip | Focus it and press **Alt + ←** / **Alt + →**, or select it and use **Move scene earlier** / **Move scene later** |
| Reorder lanes | The ↑ / ↓ buttons next to each name under **Lanes** |
| Place an unplaced card | Pick its scene in the panel (Narrative), or **Place on axis** (Chronology) |

On the Chronology axis, a step moves a card past the neighbouring column of story time.

## The room on the map

The map is a chat focus. Open a card or a shared moment, or click a character's name in their lane
header to select the lane, and the [chat](chat.md) knows what you are looking at. Ask about it in
plain words:

- "Where is Will's emotional low?" The room reads the map and names the cards.
- "Give Josephine a reason to be here." It proposes a **motivation** on her card.
- "Move the confrontation before the funeral." It proposes a scene reorder, which appears here as
  ghosts until you apply it.

The room only ever proposes. Card changes and shared moments arrive under **For your review** in
the chat (and on the writers' room page), and nothing on the map changes until you approve them.
A shared moment the room proposes merges its cards only when you approve it; rolling it back takes
everyone out of it again.

When the room reads the map, the chat shows a **Journey map** card: a small strip of each lane's
cards, coloured by intensity, with the arc check's findings.

### Develop the story

In **Develop the story** ([writers' room](writers-room.md)), each lead's timeline arrives with an
intensity and a motivation on every card. After you approve the timelines, the story editor looks
for the moments the leads share and proposes them as shared moments, one proposal each. Run only
the **timelines** stage to do this for the cast you already have.

### Arc check

**Arc check** in the writers' room reads the map and reports, per character:

| Finding | Means |
|---|---|
| Flat arc | the lane's intensity stays within one step across its cards |
| Never turns | the intensity only rises or only falls (three cards or more) |
| Never crosses the protagonist | the character shares no moment and no scene with the lead (the character whose role is protagonist) |
| Too few cards | fewer than two cards, too few to read an arc |

The findings are measured from the cards, so the same map always gets the same findings. The
character specialist then explains each one with card ids and suggests a fix. The check is a
report; it changes nothing.
