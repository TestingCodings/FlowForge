Feature: YAML text-first authoring
  As a power user
  I want to author workflows as YAML with a live preview
  So that definitions are fast to write, diffable, and scriptable

  Background:
    Given I am signed in as "admin@flowforge.dev"

  @core
  Scenario: The YAML editor renders a live diagram from valid input
    Given I open the YAML workflow editor
    When I enter a valid workflow definition in YAML
    Then the preview shows the corresponding state nodes
    And the preview shows the transitions between them

  @core
  Scenario: Invalid YAML shows a line-referenced error
    Given I open the YAML workflow editor
    When I enter a transition referencing an unknown state
    Then I see an error naming the unknown state
    And the create action is disabled while the definition is invalid

  @core
  Scenario: Creating a workflow from YAML
    Given I open the YAML workflow editor
    When I enter a valid workflow named "E2E YAML Flow Expense"
    And I create the workflow
    Then the workflow "E2E YAML Flow Expense" is created
