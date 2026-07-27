Feature: Scene authoring
  As a workflow designer
  I want to edit per-state scene config without hand-writing JSON
  So that scene-shell workflows stay accessible and round-trip safely

  Background:
    Given I am signed in as "admin@flowforge.dev"

  @core @sceneauthoring
  Scenario: Editing a scene-shell workflow from the workflow detail page
    Given I am viewing a throwaway scene workflow
    Then I see the scene editor populated from its existing config
    When I save the scene editor without changes
    Then I see the scene editor save successfully
    When I choose "View as YAML"
    Then the YAML contains the scene dialogue "You wake on a cold floor."
    When I close the YAML modal
    And I add a sprite row to the "Awakening" scene
    And I save the scene editor without changes
    Then I see a validation error on the "Awakening" scene sprite asset field
    When I remove the incomplete sprite from the "Awakening" scene
    And I set the "Awakening" scene speaker to "Guide"
    And I set the "Awakening" scene dialogue to "Welcome, {{instance.reference_number}}."
    And I save the scene editor without changes
    Then I see the scene editor save successfully
    When I choose "View as YAML"
    Then the YAML contains the scene speaker "Guide"
    And the YAML contains the scene dialogue "Welcome, {{instance.reference_number}}."
