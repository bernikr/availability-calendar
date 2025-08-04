# Availability Calendar

Create an ical calendar with your availability based on multiple source ical calendars.

## Usage and Configuration

`compose.yaml`

```yaml
services:
  availability-calendar:
    image: ghcr.io/bernikr/availability-calendar:1.1.1
    environment:
      TZ: Europe/Vienna # optional defaults to Europe/Vienna
    volumes:
      - ./config.yaml:/config.yaml
    ports:
      - 8000:8000
```

`config.yaml`

```yaml  
calendars:
  work: # the name of the calendar (will be used as the filename)
    key: <private key> # optional, if set the calendar will only be accessible with the key
    days_ahead: 7 # optional, defaults to 28, how far into the future to include events
    sources:
      - url: <url to ical calendar>
        event_name: "I'm busy" # optional, defaults to "Busy"
      - url: <url to ical calendar>
        include: # optional, icalendar keys to include in the calendar
          - SUMMARY # use the title of the event
  private: # the name of the calendar (will be used as the filename)
    key: # also supports multiple keys in case you want to revoke one later
      - <private key>
      - <another private key>
    sources:
      - url: <url to ical calendar>
        filter: # optional
          name_regex: "[^\\?]$" # optional, regex to filter events by name (example: hide events with a question mark at the end)
      - url: <url to ical calendar>
        hide_if_overlapped: true # optional, hides events that are completely covered by another event
        tentative: true # optional, show the event as tentative in supported clients
```

The ical will then be available at `http://localhost:8000/work.ics?key=<private key>`
