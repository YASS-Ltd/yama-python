# Reference

Everything public is importable from `yama`, except `fake_transport`, which is in `yama.testing`. Models and enums are also in `yama.models`.

## Client

::: yama.Yama

::: yama.DEFAULT_BASE_URL

## Resources

The client's attributes. Each method is one API operation.

::: yama._resources.ApiKeyResource

::: yama._resources.Buildings

::: yama._resources.Units

::: yama._resources.Contacts

::: yama._resources.Codes

::: yama._resources.Calls

## Models

::: yama.models
    options:
      show_root_heading: false
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
