Feature: Workspace configuration
  As a platform admin
  I want to configure workspace-wide branding and preferences
  So that FlowForge looks and behaves like our own tool

  Background:
    Given I am signed in as "admin@flowforge.dev"

  @core
  Scenario: Changing the theme preset restyles the platform
    Given I am on the workspace settings page
    When I apply the "Daylight" theme preset and save
    Then the platform adopts the new theme colours

  @core
  Scenario: Switching the language translates the navigation
    Given I am on the workspace settings page
    When I set the language to "Español" and save
    Then the sidebar navigation appears in Spanish
    And the document language is "es-ES"

  @core
  Scenario: Compact density tightens spacing
    Given I am on the workspace settings page
    When I set the density to "Compact" and save
    Then the interface uses the compact spacing

  @full
  Scenario: An invalid workspace value is rejected
    Given I am on the workspace settings page
    When a language outside the supported set is submitted
    Then the server rejects it with a validation message

  @full
  Scenario: Non-admins cannot change workspace settings
    Given I am signed in as a participant
    When I attempt to open workspace settings
    Then I do not have access to change them
