Feature: Authentication
  As a user of FlowForge
  I want to sign in and out securely
  So that my workspace and its data are protected

  Background:
    Given the FlowForge app is running with seeded demo accounts

  @smoke
  Scenario: Signing in with valid credentials
    Given I am on the login page
    When I sign in as "admin@flowforge.dev" with password "Admin1234!"
    Then I land on the dashboard
    And the sidebar shows my workspace navigation

  @core
  Scenario: Signing in with an incorrect password is rejected
    Given I am on the login page
    When I sign in as "admin@flowforge.dev" with password "wrong-password"
    Then I see an authentication error
    And I remain on the login page

  @core
  Scenario: Protected pages redirect an unauthenticated visitor to login
    Given I am not signed in
    When I navigate to "/workflows"
    Then I am redirected to the login page

  @core
  Scenario: Signing out returns to the login page
    Given I am signed in as "admin@flowforge.dev"
    When I sign out
    Then I return to the login page
    And navigating to "/dashboard" redirects me back to login
