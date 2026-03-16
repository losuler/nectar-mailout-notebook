{% if instances -%}
## Affected Instances

| ID | Name | IP Addresses | Status |
|---|---|---|---|
{% for instance in instances -%}
{% set ip_list = [] -%}
{% for network in instance.addresses.values() -%}
    {% for ip in network -%}
        {% set _ = ip_list.append(ip.addr) -%}
    {% endfor -%}
{% endfor -%}
| {{ instance.id }} | {{ instance.name }} | {{ ip_list | join(', ') }} | {{ instance.status }} |
{% endfor -%}
{% endif %}