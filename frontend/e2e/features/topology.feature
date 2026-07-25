Feature: Topology view
  As a user managing connected systems
  I want a map of instances and how they link across workflows
  So that I can see the real connections between assets, not just one lifecycle

  Background:
    Given I am signed in as "admin@flowforge.dev"

  @smoke
  Scenario: The topology view renders the estate as a graph
    When I open the topology view
    Then I see connected instance nodes on the map
    And the legend explains relationship and containment edges

  @core
  Scenario: Focusing the topology on one instance
    Given I am viewing an instance with relationships
    When I choose "View topology"
    Then the map is rooted at that instance
    And I can widen the depth to reveal further connections
