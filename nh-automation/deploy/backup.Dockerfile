# Nightly pg_dump service (P0-5). Alpine's postgres image ships pg_dump and
# busybox crond, which is all this needs.
FROM postgres:16-alpine

COPY backup.sh /usr/local/bin/backup.sh
COPY crontab /etc/crontabs/root
RUN chmod +x /usr/local/bin/backup.sh

CMD ["crond", "-f", "-l", "2"]
