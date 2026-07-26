Feature: Presentation shells
  As a workflow designer
  I want to present a workflow through different shells
  So that each process looks like the tool its users expect

  Background:
    Given I am signed in as "admin@flowforge.dev"

  @smoke
  Scenario: A kanban workflow renders columns per state
    Given the "Bug Report" workflow uses the "kanban" shell
    When I open its view
    Then I see a column for each workflow state
    And each card links to its instance

  @core @wip
  Scenario: Dragging a card fires the matching transition
    Given the "Bug Report" workflow uses the "kanban" shell
    And I am viewing its board
    When I drag a card to an adjacent state column
    Then the instance moves to that state
    And the card appears under the new column

  @core
  Scenario: The table shell shows configured columns
    Given a workflow configured with the "table" shell and columns "reference, state, created"
    When I open its view
    Then the table header shows "Reference", "State" and "Created"

  @core
  Scenario: The matrix shell lays instances out as rows by columns
    Given the "Test Run" workflow uses the "matrix" shell grouped by suite and state
    When I open its view
    Then I see a row per suite
    And I see a column per state
    And cells show state-coloured instance chips

  @core
  Scenario: The list shell renders a filterable list
    Given a workflow configured with the "list" shell
    When I open its view
    And I filter the list by a reference substring
    Then only matching instances remain

  @core @wip
  Scenario: The stepped-form shell walks an instance through its states
    Given the "Insurance Claim" workflow uses the "stepped_form" shell
    When I open its view and select an instance at a form state
    Then I see a progress stepper of the states
    And I see the current state's form as a focused card
    And the advance buttons are disabled until the required form is submitted

  @full
  Scenario: Exporting a board view as a PNG image
    Given I am viewing a workflow in the builder
    When I choose export as PNG
    Then a PNG image of the canvas is downloaded
