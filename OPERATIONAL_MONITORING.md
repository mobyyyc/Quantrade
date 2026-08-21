# Operational Monitoring

P7.1 monitors normalized operational state without changing published scores.

- **Freshness:** the latest regular-session price date and score date must meet
  the expected completed market session.
- **Failures:** any failed or unreadable run manifest is critical.
- **Score anomalies:** zero eligible names is critical. A greater than 30%
  eligible-count drop or greater than 20-point mean-score shift from the prior
  run is a warning for investigation.

`PostgresOperationalMonitor` is read-only. Connect it with `DATABASE_URL`, pass
the expected completed session date, and retain manifests from each pipeline
run in a durable directory. A critical alert blocks publication and requires
the recovery process defined in P7.2.
