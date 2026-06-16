# FlowForge User Guide

## What This Guide Covers

This guide explains how to use FlowForge as an end user and as an admin/designer:
- Sign in and navigate the app
- Create workflows quickly by category
- Create a full starter set of workflows in one click
- Start and progress instances
- Work with forms, tasks, and audit logs

## 1. Sign In and Access

1. Open the frontend app.
2. Register a user on `/register` (if needed).
3. Sign in on `/login`.
4. After login, you are redirected to `/dashboard`.

## 2. Main Screens

- Dashboard: task inbox for the current user
- Workflows: list of workflow definitions
- New Workflow: quick creation tools (category + full set)
- Instances: list and details for running workflow instances
- Audit (admin): global audit events
- Users (admin): user administration placeholder (Django admin can be used)

## 3. Quick Workflow Creation by Category

Open `/workflows/new`.

### Create Any Single Category

1. Select a category from the Category dropdown:
   - Insurance
   - HR
   - Engineering
   - Finance
2. Click `Create Category Workflow`.
3. A new workflow is created with that category template.

### Create a Full Set in One Action

1. Click `Create Full Set`.
2. FlowForge will attempt to create all category templates in sequence.
3. The result message shows which categories succeeded or failed.

Notes:
- Workflow names include a timestamp suffix to avoid name collisions.
- If one category fails, the others still continue.

## 4. Running a Workflow Instance

1. Go to `/instances`.
2. Open or create an instance via API/admin as needed.
3. On the instance detail page (`/instances/:id`), use `Advance Instance`.
4. State transitions run workflow rules and can create tasks/notifications.

## 5. Forms and Tasks

- Forms are attached to workflow states.
- Submissions are validated against schema rules.
- Tasks are generated from workflow state/task config and must be completed by the right user/role.

## 6. Audit and Notifications

- Every major action is audit logged.
- Notification templates can be configured for events:
  - instance created
  - state transition
  - task assigned/completed
  - form submitted

## 7. Troubleshooting

- 401/redirect to login: token expired or missing; sign in again.
- Cannot access admin pages: account lacks platform admin role.
- Workflow creation fails: check API validation errors (state/transition schema, unique names).
- Full set partial success: retry failed categories individually.

## 8. Recommended Admin Setup

1. Create platform admin user.
2. Seed category workflows from `/workflows/new`.
3. Add form definitions and notification templates.
4. Assign user roles before production use.
