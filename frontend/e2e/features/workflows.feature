Feature: Workflow catalogue
  As a workflow designer
  I want to browse and inspect workflow definitions
  So that I can understand and manage the processes on the platform

  Background:
    Given I am signed in as "admin@flowforge.dev"

  @smoke
  Scenario: The workflows list shows the seeded definitions
    When I open the workflows page
    Then I see a workflow named "Bug Report"
    And I see a workflow named "Insurance Claim"
    And I see a workflow named "Test Run"

  @core
  Scenario: Opening a workflow shows its state graph and settings
    Given I am on the workflows page
    When I open the "Bug Report" workflow
    Then I see the workflow's state diagram
    And I see the "Edit in Builder" action
    # "Open <shell> view" — Bug Report is seeded with no ui_schema, so it is
    # the default list shell. This said "kanban", which only ever passed
    # because a shell scenario had mutated Bug Report first; once those
    # scenarios got their own fixtures the borrowed state disappeared.
    And I see the "Open list view" action

  @core
  Scenario: Exporting a workflow as a portable bundle
    Given I am viewing the "Bug Report" workflow
    When I export the workflow
    Then a ".flowforge.json" bundle is downloaded

  @core
  Scenario: Viewing a workflow as YAML
    Given I am viewing the "Bug Report" workflow
    When I choose "View as YAML"
    Then I see the workflow rendered as YAML text
    And the YAML contains the workflow's states and transitions
