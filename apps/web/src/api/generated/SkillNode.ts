/* Generated from docs/schemas. Do not edit by hand. */

/**
 * Expected difficulty from 1 to 5 for this skill in this preparation; set on leaves only.
 */
export type Difficulty = number | null;
/**
 * Stable UUIDv5 identity derived from this node's root and normalized label.
 */
export type Id = string;
/**
 * Importance from 1 to 5 for this skill in this preparation; set on leaves only.
 */
export type Importance = number | null;
/**
 * Short display label for this category or technical skill.
 */
export type Label = string;
/**
 * ID of this node's parent, or None when this node is a root category.
 */
export type ParentId = string | null;

/**
 * One category, intermediate node, or leaf in a preparation's skill tree.
 */
export interface SkillNode {
  difficulty: Difficulty;
  id: Id;
  importance: Importance;
  label: Label;
  parent_id: ParentId;
}
