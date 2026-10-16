# Reference

Everything here is importable from `yama`, except the resources below, and `fake_transport`, which is in `yama.testing`. Models and enums are also in `yama.models`.

## Client

::: yama.Yama

::: yama.DEFAULT_BASE_URL

## Resources

The client's attributes, such as `client.codes`; you don't create these yourself. Each method is one API operation.

### client.api_key { #api-key }

::: yama._resources.ApiKeyResource
    options:
      show_root_heading: false
      show_root_toc_entry: false
      show_bases: false
      heading_level: 4

### client.buildings { #buildings }

::: yama._resources.Buildings
    options:
      show_root_heading: false
      show_root_toc_entry: false
      show_bases: false
      heading_level: 4

### client.units { #units }

::: yama._resources.Units
    options:
      show_root_heading: false
      show_root_toc_entry: false
      show_bases: false
      heading_level: 4

### client.contacts { #contacts }

::: yama._resources.Contacts
    options:
      show_root_heading: false
      show_root_toc_entry: false
      show_bases: false
      heading_level: 4

### client.codes { #codes }

::: yama._resources.Codes
    options:
      show_root_heading: false
      show_root_toc_entry: false
      show_bases: false
      heading_level: 4

### client.calls { #calls }

::: yama._resources.Calls
    options:
      show_root_heading: false
      show_root_toc_entry: false
      show_bases: false
      heading_level: 4

## Models

::: yama.models
    options:
      show_root_heading: false
      show_root_toc_entry: false
      members_order: source

## Errors

::: yama
    options:
      show_root_heading: false
      show_root_toc_entry: false
      members:
        - YamaError
        - APIConnectionError
        - APITimeoutError
        - APIStatusError
        - BadRequestError
        - AuthenticationError
        - PermissionDeniedError
        - NotFoundError
        - ConflictError
        - GoneError
        - UnprocessableEntityError
        - RateLimitError
        - ServerError

## Testing

::: yama.testing.fake_transport
