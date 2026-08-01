Feature: Instance lifecycle
  As a participant
  I want to create instances and move them through their workflow
  So that real work progresses under the rules the workflow defines

  Background:
    Given I am signed in as "admin@flowforge.dev"

  @smoke
  Scenario: The instances list shows seeded instances
    When I open the instances page
    Then I see at least one instance reference number

  @core
  Scenario: Opening an instance shows its detail and timeline
    Given I am on the instances page
    When I open the first instance
    Then I see its state diagram
    And I see the "Timeline" panel
    And I see the available transition actions

  @core
  Scenario: Firing an available transition advances the instance
    Given I am viewing an open instance with an available transition
    When I fire the transition
    Then the instance's current state updates
    And the timeline records the transition

  @core
  Scenario: A transition blocked by a rule surfaces the reason
    Given I am viewing an instance whose transition is blocked by a rule
    When I attempt the blocked transition
    Then I see the reason the transition was blocked
    And the instance stays in its current state

  @core
  Scenario: Editing metadata records an audit entry
    Given I am viewing an open instance
    When I edit a metadata value and save
    Then the metadata shows the new value
    And the timeline records a metadata update

  @full
  Scenario: Concurrent metadata edits are protected by optimistic locking
    Given I am viewing an open instance
    And the instance was modified elsewhere after I loaded it
    When I save my metadata change
    Then I am warned the instance changed and shown the current values

  @full
  Scenario: Linking one instance to another
    Given I am viewing an open instance
    When I link it to another instance by reference
    Then the relationship appears in the Relationships panel
