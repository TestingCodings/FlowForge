Feature: State forms
  As a participant
  I want to complete the form a state requires
  So that captured data gates progress and feeds the rules engine

  Background:
    Given I am signed in as "admin@flowforge.dev"

  @core
  Scenario: A required form blocks its transition until submitted
    Given I am viewing an instance whose current state has a required form
    Then the transition gated by the form is unavailable
    When I complete and submit the form
    Then the gated transition becomes available

  @core
  Scenario: Form validation rejects missing required fields
    Given I am viewing an instance with a required form
    When I submit the form with a required field empty
    Then I see a validation error on that field

  @core
  Scenario: Submitted form values merge into instance metadata
    Given I am viewing an instance with a form
    When I submit the form with values
    Then those values appear in the instance metadata
