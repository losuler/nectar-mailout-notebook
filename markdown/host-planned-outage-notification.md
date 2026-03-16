{% include 'fragments/greeting.md' %}

This email is to inform you of a scheduled compute host outage to the Nectar
Research Cloud.

{% include 'fragments/schedule.md' %}

## Description

A {% if days > 0 %}{{ days }} day {% elif hours > 0 %}{{ hours }} hour {% else %} short {% endif %}
outage is required to perform essential maintenance on the cloud infrastructure
that some of your instances or databases are hosted on.

## Impact

Affected compute and databases instances will be shut down and will be
inaccessible during the outage. (Note that they will **not** be destroyed.)
In addition, management requests (e.g. 'reboot', 'resize' and 'snapshot')
for the affected instances will not work during the outage.

{% if instances -%}
Your instances that will affected by this outage are listed below.
{% endif -%}

## Actions required

We will shut down all affected compute instances that are in RUNNING, SUSPENDED
or PAUSED states when the outage commences. After the required work has been
completed, the instances that >>we<< shut down will started again.
Likewise, we will shut down and start any affected database instances.
Any loadbalancers affected by the outage should recover automatically, to
the extent possible.

We cannot undertake to shutdown or start your compute instances in any
particular order.

- We recommend that you complete your own backups, snapshots or
  otherwise save copies of important data somewhere other than the affected
  availability zones.
- After the outage, we advise that you check that you SSH to your
  servers, and check that your outward facing services have all recovered.
- If you cannot SSH to an affected compute instance, or if you observe
  database or loadbalancer issues, please contact Nectar support (as below).
- If your compute instances need to be started in a particular sequence,
  you may have to manually restart them yourself. (Please check your own
  service documentation where such issues should noted. In general, this
  is something we can't help you with.)

{% include 'fragments/affected_instances.md' %}

{% include 'fragments/signoff.md' %}