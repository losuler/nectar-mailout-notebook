from datetime import datetime
import logging
from getpass import getpass
from zoneinfo import ZoneInfo

import openstack
from taynacclient import client as taynacclient
from jinja2 import Environment, FileSystemLoader, StrictUndefined

try:
    from IPython.display import display, HTML

    HAS_IPYTHON = True
except ImportError:
    HAS_IPYTHON = False
    display = None
    HTML = None


LOG_LEVEL = logging.INFO
# LOG_LEVEL = logging.DEBUG

logging.basicConfig(format="%(message)s")
LOG = logging.getLogger(__name__)
LOG.setLevel(LOG_LEVEL)

# Set our standard time format (2026-03-06 14:45)
TIME_FORMAT = "%Y-%m-%d %H:%M"


class MailoutHelper:
    """Helper class for managing mailout notifications.

    This class provides utilities for:
    - Managing OpenStack connections
    - Querying projects, users, and roles
    - Building recipient lists
    - Rendering Jinja2 templates
    - Sending notifications via Taynac
    """

    def __init__(self, start_time=None, end_time=None, timezone="Australia/Melbourne"):
        """Initialize the MailoutHelper."""
        self._start_time = None
        self._end_time = None
        self.timezone = timezone

        if start_time:
            self._start_time = self._parse_time(start_time, timezone)
        if end_time:
            self._end_time = self._parse_time(end_time, timezone)

        self.conn = None
        self.taynac = None

        # Set up template environment using 'templates' directory
        self.template_env = Environment(
            loader=FileSystemLoader("templates"),
            trim_blocks=True,
            undefined=StrictUndefined,
        )

    def _parse_time(self, time_input, timezone):
        """Parse time string

        Args:
            time_input: A %Y-%m-%d %H:%M:%S formatted string
            timezone: A timezone string
        """
        tz = ZoneInfo(timezone)
        dt = datetime.strptime(time_input, "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=tz)
        return dt.astimezone(tz)

    def set_times(self, start_time, end_time, timezone):
        """Set the start time, end time, and timezone for notifications.

        Args:
            start_time: datetime object for the start time
            end_time: datetime object for the end time
            timezone: String representing the timezone (e.g., 'Australia/Melbourne')
        """
        self._start_time = self._parse_time(start_time, timezone)
        self._end_time = self._parse_time(end_time, timezone)
        self.timezone = timezone

    @property
    def start_time(self):
        ts = self._start_time.strftime(TIME_FORMAT)
        return f"{ts} {self.timezone}"

    @property
    def end_time(self):
        ts = self._end_time.strftime(TIME_FORMAT)
        return f"{ts} {self.timezone}"

    def setup_openstack(self, auth_url, token=None):
        """Set up OpenStack connection with token authentication.

        Args:
            auth_url: OpenStack identity URL
            token: OpenStack token (if None, will prompt for it)

        Returns:
            OpenStack connection object
        """
        if token is None:
            token = getpass(prompt="Enter your OpenStack Token: ")

        self.conn = openstack.connect(
            auth_url=auth_url,
            token=token,
            auth_type="token",
        )

        # Verify token is valid
        auth_ref = self.conn.session.auth.get_auth_ref(self.conn.session)
        print(f"Token expires at: {auth_ref.expires}")
        return self.conn

    def get_taynac_client(self):
        if self.taynac is None:
            if self.conn is None:
                raise ValueError(
                    "OpenStack connection must be set up before sending notifications"
                )
        self.taynac = taynacclient.Client(version="1", session=self.conn.session)
        return self.taynac

    def build_context(self, project_data=None):
        """Build notification context with project data and time information.

        Args:
            project_data: Dictionary containing project, managers, members, and instances

        Returns:
            Dictionary with context data including times and duration
        """

        context = {}
        if project_data:
            context = project_data.copy()

        if self._start_time and self._end_time:
            context["start_time"] = self.start_time
            context["end_time"] = self.end_time
            context["tz"] = self.timezone

            # Calculate the duration
            duration = self._end_time - self._start_time
            context["days"] = duration.days
            context["hours"] = duration.seconds // 3600

        return context

    def get_role(self, role_name):
        """Fetch role by name.

        Args:
            role_name: Name of the role to fetch

        Returns:
            Role object
        """
        LOG.debug(f"Looking for role: {role_name}")
        return next(self.conn.identity.roles(name=role_name))

    def get_project_users(self, project_id, role_id, exclude_disabled=False):
        """Get email addresses for users with certain roles in a given project.

        Args:
            project_id: ID of the project
            role_id: ID of the role to filter by
            exclude_disabled: Whether to exclude disabled users (default: False)

        Returns:
            List of user objects with the specified role
        """
        LOG.debug(f"Getting users for project: {project_id} and role: {role_id}")
        users = []

        ras = self.conn.identity.role_assignments(
            scope_project_id=project_id, role_id=role_id, include_names=True
        )
        for ra in ras:
            u = self.get_user(ra.user.get("id"))
            if exclude_disabled and not u.enabled:
                continue
            # Only include users with an email address
            if getattr(u, "email", None):
                users.append(u)
        return users

    def get_project_members(self, project_id, exclude_disabled=False):
        """Get Member role users for a project.

        Args:
            project_id: ID of the project
            exclude_disabled: Whether to exclude disabled users (default: False)

        Returns:
            List of user objects with Member role
        """
        role_id = self.get_role("Member").get("id")
        return self.get_project_users(
            project_id, role_id, exclude_disabled=exclude_disabled
        )

    def get_tenant_managers(self, project_id):
        """Get tenant manager emails for a project.

        Args:
            project_id: ID of the project

        Returns:
            List of user objects with TenantManager role
        """
        role_id = self.get_role("TenantManager").get("id")
        return self.get_project_users(project_id, role_id)

    def get_project(self, name_or_id):
        """Fetch project by name or ID.

        Args:
            name_or_id: Project name or ID

        Returns:
            Project object
        """
        LOG.debug(f"Looking for project: {name_or_id}")
        return self.conn.identity.find_project(name_or_id, ignore_missing=False)

    def get_user(self, name_or_id):
        """Fetch user by name or ID.

        Args:
            name_or_id: User name or ID

        Returns:
            User object
        """
        LOG.debug(f"Looking for user: {name_or_id}")
        return self.conn.identity.find_user(name_or_id, ignore_missing=False)

    def build_recipients(self, managers, members):
        """Generate list of recipient email addresses.

        Returns one email address as the 'to' address which would generally
        be the first Tenant Manager of the project. Every other manager or
        member will be added to the 'cc' list.

        Args:
            managers: List of manager user objects
            members: List of member user objects

        Returns:
            Tuple of (to_email, cc_emails) where to_email is a string and
            cc_emails is a list of strings
        """
        combined = (managers or []) + (members or [])
        seen = set()
        emails = []
        for user in combined:
            email = getattr(user, "email", None)
            if email and email not in seen:
                seen.add(email)
                emails.append(email)
        if not emails:
            return None, []
        return emails[0], emails[1:]

    def render_template_string(self, tmpl, context):
        """Render a template string.

        Args:
            tmpl: Jinja2 template string
            context: Dictionary of template variables

        Returns:
            Rendered string
        """
        t = self.template_env.from_string(tmpl)
        return t.render(context).strip()

    def render_template_file(self, fn, context):
        """Render body from a template file.

        Args:
            fn: Name of the template file in the template directory
            context: Dictionary of template variables

        Returns:
            Rendered body string
        """
        t = self.template_env.get_template(fn)
        return t.render(context).strip()

    def populate_data_from_instances(self, instances):
        """Build a dictionary of project, users and instances.

        Args:
            instances: List of OpenStack instance objects

        Returns:
            Dictionary keyed by project_id containing:
                - project: Project object
                - managers: List of tenant manager users
                - members: List of member users
                - instances: List of instances in this project
        """
        data = {}
        for instance in instances:
            project_id = instance["project_id"]
            if project_id not in data:
                data[project_id] = {
                    "project": self.get_project(project_id),
                    "managers": self.get_tenant_managers(project_id),
                    "members": self.get_project_members(project_id),
                    "instances": [],
                }
            data[project_id]["instances"].append(instance)
        return data

    def generate_notifications_from_instances(self, instance_data, subject, body):
        """Generate notification content.

        Args:
            subject_template: Jinja2 template string for subject
            body_template: Jinja2 template filename for body
            to_email: Email address string for primary recipient
            cc_emails: List of CC Email address strings

        Returns:
            Dictionary containing subject, body, to, cc,
        """
        notifications = []
        for project_id, project_data in instance_data.items():
            # Build context with time information
            context = self.build_context(project_data)

            # Build recipient list from OpenStack project Tenant Managers
            # and Members
            to_email, cc_emails = self.build_recipients(
                project_data["managers"], project_data["members"]
            )

            rendered_body = self.render_template_file(body, context)
            rendered_subject = self.render_template_string(subject, context)

            # Generate notification
            notifications.append(
                {
                    "subject": rendered_subject,
                    "body": rendered_body,
                    "to": to_email,
                    "cc": cc_emails,
                }
            )
        return notifications

    def preview_notification(self, notification):
        """Preview a notification in the notebook or CLI.

        Args:
            notification: Dictionary containing 'subject', 'body', 'to', and 'cc'
        """
        if HAS_IPYTHON:
            display(notification.get("to"))
            display(notification.get("cc", "N/A"))
            display(HTML(notification["subject"]))
            display(HTML(notification["body"]))
        else:
            print(f"To: {notification.get('to')}")
            print(f"CC: {notification.get('cc', [])}")
            print(f"Subject: {notification['subject']}")
            print(f"Body: {notification['body']}")

    def send_notification(self, notification):
        """Send notification via Taynac.

        Args:
            notification: Dictionary containing 'subject', 'body', 'to', and 'cc'
        """
        taynac = self.get_taynac_client()
        taynac.messages.send(
            subject=notification["subject"],
            body=notification["body"],
            recipient=notification["to"],
            cc=notification.get("cc", []),
        )
