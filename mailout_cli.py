#!/usr/bin/env python3
import argparse
import sys
from getpass import getpass

from mailout_helper import MailoutHelper


def parse_args():
    parser = argparse.ArgumentParser(
        description="Send notification emails to OpenStack project users via Taynac."
    )
    parser.add_argument(
        "--openstack-url",
        default="https://identity.rc.nectar.org.au/",
        help="OpenStack identity URL",
    )
    parser.add_argument(
        "--use-app-credentials",
        action="store_true",
        help="Use application credentials instead of token",
    )
    parser.add_argument(
        "--app-credential-id",
        help="Application credential ID (prompts if not provided with --use-app-credentials)",
    )
    parser.add_argument(
        "--app-credential-secret",
        help="Application credential secret (prompts if not provided with --use-app-credentials)",
    )
    parser.add_argument(
        "--openstack-token",
        help="OpenStack token (prompts if not provided)",
    )
    parser.add_argument(
        "--project",
        action="append",
        required=True,
        help="Project name or ID (can be specified multiple times)",
    )
    parser.add_argument(
        "--role",
        choices=["Member", "TenantManager", "both"],
        default="both",
        help="Filter users by role (default: both)",
    )
    parser.add_argument(
        "--exclude-disabled",
        action="store_true",
        help="Exclude disabled users",
    )
    parser.add_argument(
        "--subject",
        required=True,
        help="Email subject (Jinja2 template)",
    )
    parser.add_argument(
        "--body",
        help="Email body as inline text (Jinja2 template)",
    )
    parser.add_argument(
        "--body-file",
        help="Email body from template file in templates/ or markdown/ directory (use 'markdown/...' for markdown templates)",
    )
    parser.add_argument(
        "--start-time",
        help="Outage start time (YYYY-MM-DD HH:MM:SS)",
    )
    parser.add_argument(
        "--end-time",
        help="Outage end time (YYYY-MM-DD HH:MM:SS)",
    )
    parser.add_argument(
        "--timezone",
        default="Australia/Melbourne",
        help="Timezone (default: Australia/Melbourne)",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        default=True,
        help="Preview notifications (default)",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send notifications (default is preview only)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.body is None and args.body_file is None:
        print("Error: either --body or --body-file must be provided")
        sys.exit(1)

    if args.send and args.preview:
        print("Error: cannot use both --preview and --send")
        sys.exit(1)

    if not args.send and not args.preview:
        print("Error: must use either --preview or --send")
        sys.exit(1)

    use_app_creds = args.use_app_credentials
    app_cred_id = args.app_credential_id
    app_cred_secret = args.app_credential_secret

    if use_app_creds:
        if app_cred_id is None:
            app_cred_id = getpass(prompt="Enter your Application Credential ID: ")
        if app_cred_secret is None:
            app_cred_secret = getpass(
                prompt="Enter your Application Credential Secret: "
            )
    else:
        token = args.openstack_token
        if token is None:
            token = getpass(prompt="Enter your OpenStack Token: ")

    helper = MailoutHelper(
        start_time=args.start_time,
        end_time=args.end_time,
        timezone=args.timezone,
    )

    print(f"Connecting to OpenStack at {args.openstack_url}...")
    helper.setup_openstack(
        args.openstack_url,
        use_app_credentials=use_app_creds,
        app_credential_id=app_cred_id,
        app_credential_secret=app_cred_secret,
        token=token if not use_app_creds else None,
    )

    action = "send" if args.send else "preview"
    print(
        f"Fetching users for {len(args.project)} project(s) and {args.role} role(s)..."
    )

    for project_name in args.project:
        project = helper.get_project(project_name)
        print(f"  Project: {project.name} ({project.id})")

        managers = []
        members = []

        if args.role in ("TenantManager", "both"):
            managers = helper.get_tenant_managers(project.id)
            print(f"    TenantManagers: {len(managers)}")

        if args.role in ("Member", "both"):
            members = helper.get_project_members(
                project.id, exclude_disabled=args.exclude_disabled
            )
            print(f"    Members: {len(members)}")

        to_email, cc_emails = helper.build_recipients(managers, members)

        if to_email is None:
            print(f"  No recipients found, skipping...")
            continue

        context = helper.build_context(
            {"project": project, "managers": managers, "members": members}
        )

        if args.body_file:
            body = helper.render_template_file(args.body_file, context)
        else:
            body = helper.render_template_string(args.body, context)

        subject = helper.render_template_string(args.subject, context)

        notification = {
            "subject": subject,
            "body": body,
            "to": to_email,
            "cc": cc_emails,
        }

        print(f"  To: {to_email}")
        print(f"  CC: {cc_emails}")
        print(f"  Subject: {subject}")

        if args.send:
            print(f"  Sending notification...")
            helper.send_notification(notification)
            print(f"  Sent!")
        else:
            print(f"  Previewing notification...")
            helper.preview_notification(notification)
            print(f"  Preview complete.")

    print("Done.")


if __name__ == "__main__":
    main()
