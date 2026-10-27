# Visual tools

The visual tools draw your story from the data you already keep: your scenes, your outline's beats,
your characters' timeline events and the moments they share. Open them from **Visuals** in the
project's tools bar (`/projects/<id>/visuals`). They follow the draft you have chosen in the script,
and they update live as you or the room change the story.

Most tools need a little data first:

- **Intensity** lives on each character's timeline event, from −5 (a low) to +5 (a high).
- An event counts for a scene when it is linked to that scene, or to a **shared moment** that is.
- A beat's **type** (inciting incident, midpoint, climax and so on) makes it a milestone.
- Scene runtimes are the same estimate as the timeline board's: about two words a second, and at
  least 30 seconds a scene.

## Tension curve

A line through the script, scene by scene in narrative order, at the average intensity of every
event in each scene. Scenes without rated events leave a gap in the line. Act breaks are marked,
and so is each typed beat, at the first of its linked scenes. Typed beats that are not linked to a
scene yet are listed under the chart. The table below the chart holds the same data; hover or focus
a row to find its scene on the curve.

## Relationship graph

Your cast as a ring. The more moments two characters share, the thicker the line between them;
scenes they share count a little. Dashed lines are links with no shared moment, only shared scenes
or a named relationship (from **Characters → Relationships**). Choose a character to see only their
links, ranked by strength.

## Corkboard

Your outline's beats as index cards, one column per act, with beats in no act in their own column.
Focus a card and use the arrow keys: up and down move it within its act, left and right move it to
the previous or next act. Each card also has buttons for the same moves. Every move is saved to the
outline at once, so the Outline page shows the same order.

## Structure templates

Choose **Save the Cat**, the **Hero's Journey** or **Five acts** to lay it over your outline. The
track shows where each target beat usually falls in the runtime, and where your beats fall, at the
start of their first linked scene. The table matches each target to one of your beats, by title
first and then by beat type.

Nothing changes until you ask. **Add missing beats to the outline** lists the targets you don't
have and, once you confirm, adds them as planned beats in the matching act (or your last act, if
the template has more acts than your draft). Edit, move or delete them on the Outline like any
other beat.

## Pacing heatmap

One row per act. Each cell is a scene, as wide as its share of the act's runtime and coloured by
its intensity: blue for lows, red for highs, grey without rated events. The table gives each act's
runtime, share of the script, runtime-weighted average intensity and its strongest peak.

## For agents and MCP clients

The same data is one read: `GET /api/v1/projects/<id>/visuals` (optionally `?screenplay_id=`), or
the read-only MCP tool `read_story_visuals`. Agents never change your outline from here; applying a
template is always your own action.
