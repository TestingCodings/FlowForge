Feature: Dashboard
  As a signed-in user
  I want an overview of platform activity
  So that I can see the state of my work at a glance

  Background:
    Given I am signed in as "admin@flowforge.dev"

  @smoke
  Scenario: The dashboard shows summary statistics
    When I open the dashboard
    Then I see the "Active Instances" stat
    And I see the "Completed" stat
    And I see the "Workflows" stat

  @core
  Scenario: The dashboard charts recent activity
    When I open the dashboard
    Then I see the "Activity" chart
    And I see the "Instances by current state" breakdown
