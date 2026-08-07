Feature: Capability-gated navigation
  As someone using a workflow rather than building one
  I want to be shown only what I can actually do
  So that the app fits my job instead of the designer's

  @core
  Scenario: An administrator sees the whole shell
    Given I am signed in as "admin@flowforge.dev"
    When I look at the sidebar
    Then it offers workspace administration

  @core
  Scenario: A role without administration rights is not shown it
    # The complaint this answers: everyone saw the designer's interface, so a
    # participant was shown builder links and admin pages that refused them
    # on arrival.
    Given I am signed in as a user holding only "instance.view" and "workflow.view"
    When I look at the sidebar
    Then it does not offer workspace administration
    And it does not offer workflow authoring
    And it still offers the pages I can use

  @core
  Scenario: A section with nothing left in it disappears
    Given I am signed in as a user holding only "instance.view" and "workflow.view"
    When I look at the sidebar
    Then no section heading stands alone with nothing under it

  @core
  Scenario: A custom role is gated on what it was actually given
    # The case the old frontend map could not express. It knew only the five
    # built-in roles, so a custom role matched nothing and its holder was
    # treated as having no capabilities at all.
    Given I am signed in as a user holding only "instance.view" and "workflow.design"
    When I look at the sidebar
    Then it offers workflow authoring
    And it does not offer workspace administration
