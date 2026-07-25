Feature: Visual workflow builder
  As a workflow designer
  I want to build and edit workflows on a visual canvas
  So that I can model processes without writing code

  Background:
    Given I am signed in as "admin@flowforge.dev"

  @smoke
  Scenario: The builder opens with an initial state
    When I open the workflow builder
    Then the canvas shows one state node marked "Start"
    And the toolbar shows the Save, Add State, and Auto-layout controls

  @core
  Scenario: Adding a state and connecting a transition
    Given I am in the workflow builder on a fresh canvas
    When I add a new state
    And I connect a transition from the start state to the new state
    And I name the transition "Proceed"
    Then the canvas shows a transition labelled "Proceed"
    And the transition leaves the right side of the start state

  @core
  Scenario: Undo reverses adding a state
    Given I am in the workflow builder on a fresh canvas
    When I add a new state
    And I press undo
    Then the canvas shows only the start state

  @core
  Scenario: Validation blocks saving an incomplete workflow
    Given I am in the workflow builder on a fresh canvas
    When I save the workflow without a name
    Then I see a validation error requiring a workflow name

  @core
  Scenario: Saving a valid new workflow
    Given I am in the workflow builder on a fresh canvas
    When I name the workflow "E2E Builder Flow" with prefix "E2E"
    And I add a terminal state named "Done"
    And I connect a transition from the start state to "Done" named "Finish"
    And I save the workflow
    Then the workflow is created and I land on its detail page

  @core
  Scenario: A draft is offered after leaving the builder mid-edit
    Given I am in the workflow builder on a fresh canvas
    When I name the workflow "Unfinished Draft"
    And I leave and reopen the builder
    Then I am offered to resume the draft
    And resuming restores the workflow name "Unfinished Draft"

  @full
  Scenario: Editing an existing workflow with no instances updates it in place
    Given a workflow "E2E Editable" with no instances exists
    When I open it in the builder
    And I rename a state and save
    Then the change is saved without creating a new version

  @full
  Scenario: Editing a workflow with instances offers a new version
    Given I open the "Bug Report" workflow in the builder
    When I change a state and save
    Then I am told the workflow has instances
    And I am offered to publish a new version with my changes
