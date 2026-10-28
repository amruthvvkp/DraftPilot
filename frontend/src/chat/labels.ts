/** Writer-facing names for the tools the room uses. */
export const TOOL_LABELS: Record<string, string> = {
  read_project_overview: 'Read the project overview',
  read_story_twin: 'Checked the Story twin',
  read_story_context: 'Checked the Story twin',
  read_screenplay_scenes: 'Read scenes',
  read_scene: 'Read a scene',
  retrieve_project_context: 'Searched the project',
  read_project_artifacts: 'Read the story artifacts',
  read_character: 'Read a character',
  read_outline: 'Read the outline',
  list_story_entities: 'Listed the story',
  consult: 'Consulted a specialist',
  consult_many: 'Consulted specialists',
  plan: 'Made a plan',
  propose_screenplay_change: 'Proposed a script change',
  propose_story_change: 'Proposed a story change',
  propose_outline: 'Proposed an outline',
  start_room_workflow: 'Started a room workflow',
  start_evaluation: 'Started an evaluation',
  create_story_entity: 'Added to the story',
  update_story_entity: 'Edited the story',
  create_scene: 'Wrote a new scene',
  write_scene: 'Rewrote a scene',
  update_project: 'Updated the project',
  navigate: 'Opened a page',
  open_scene: 'Opened a scene',
}

export const ROLE_LABELS: Record<string, string> = {
  showrunner: 'Showrunner', story_editor: 'Story editor', script_doctor: 'Script doctor', scene_writer: 'Scene writer',
  brainstormer: 'Brainstormer', story_architect: 'Story architect', character_specialist: 'Character specialist',
  audience_evaluator: 'Audience evaluator', coverage_reader: 'Coverage reader', continuity_supervisor: 'Continuity supervisor', twin_keeper: 'Twin keeper',
  researcher: 'Researcher', associate_director: 'Associate director',
}

export const toolLabel = (name: string) => TOOL_LABELS[name] ?? name.replace(/_/g, ' ')
export const roleLabel = (role: string) => ROLE_LABELS[role] ?? role.replace(/_/g, ' ')
