Feature: User administration
  As a platform admin
  I want to see who has access and what they may do
  So that I can hand out and take back permissions deliberately

  Background:
    Given I am signed in as "admin@flowforge.dev"

  @core
  Scenario: The user list renders
    Given I am on the user administration page
    Then I see every user with the roles they hold

  @core
  Scenario: The shell survives a visit to the user list
    # This is the regression that mattered. AppLayout and the users page both
    # read the ["users"] cache key but disagreed about its shape, so opening
    # this page replaced an array with a paginated object and the sidebar's
    # filter threw, blanking the entire application. The page had never once
    # rendered. Navigating in and back out is what reproduces it.
    Given I am on the user administration page
    When I move to the dashboard and back to user administration
    Then the navigation shell stayed up throughout

  @core
  Scenario: Roles offered come from the role table
    Given I am on the user administration page
    When I open the role editor for a user
    Then every role defined in the workspace is offered
