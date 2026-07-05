# Senior Exemplars — Match the rhythm of these

> Selected from https://github.com/pallets/werkzeug: representative functions/classes that
> demonstrate the codebase's typical structure, type annotation density,
> and docstring style. Match this rhythm when generating new code.

## Exemplar 1: `src/werkzeug/exceptions.py:266-335` (`Unauthorized`)

**Layer**: shared | **Role**: other | **Why chosen**: fully type-annotated, rich multi-section docstring, sweet-spot length (70 lines)

```python
class Unauthorized(HTTPException):
    """*401* ``Unauthorized``

    Raise if the user is not authorized to access a resource.

    The ``www_authenticate`` argument should be used to set the
    ``WWW-Authenticate`` header. This is used for HTTP basic auth and
    other schemes. Use :class:`~werkzeug.datastructures.WWWAuthenticate`
    to create correctly formatted values. Strictly speaking a 401
    response is invalid if it doesn't provide at least one value for
    this header, although real clients typically don't care.

    :param description: Override the default message used for the body
        of the response.
    :param www-authenticate: A single value, or list of values, for the
        WWW-Authenticate header(s).

    .. versionchanged:: 2.0
        Serialize multiple ``www_authenticate`` items into multiple
        ``WWW-Authenticate`` headers, rather than joining them
        into a single value, for better interoperability.

    .. versionchanged:: 0.15.3
        If the ``www_authenticate`` argument is not set, the
        ``WWW-Authenticate`` header is not set.

    .. versionchanged:: 0.15.3
        The ``response`` argument was restored.

    .. versionchanged:: 0.15.1
        ``description`` was moved back as the first argument, restoring
         its previous position.

    .. versionchanged:: 0.15.0
        ``www_authenticate`` was added as the first argument, ahead of
        ``description``.
    """

    code = 401
    description = (
        "The server could not verify that you are authorized to access"
        " the URL requested. You either supplied the wrong credentials"
        " (e.g. a bad password), or your browser doesn't understand"
        " how to supply the credentials required."
    )

    def __init__(
        self,
        description: str | None = None,
        response: SansIOResponse | None = None,
        www_authenticate: None | (WWWAuthenticate | t.Iterable[WWWAuthenticate]) = None,
    ) -> None:
        super().__init__(description, response)

        from .datastructures import WWWAuthenticate

        if isinstance(www_authenticate, WWWAuthenticate):
            www_authenticate = (www_authenticate,)

        self.www_authenticate = www_authenticate

    def get_headers(
        self,
        environ: WSGIEnvironment | None = None,
        scope: dict[str, t.Any] | None = None,
    ) -> list[tuple[str, str]]:
        headers = super().get_headers(environ, scope)
        if self.www_authenticate:
            headers.extend(("WWW-Authenticate", str(x)) for x in self.www_authenticate)
        return headers
```

## Exemplar 2: `src/werkzeug/datastructures/auth.py:17-140` (`Authorization`)

**Layer**: shared | **Role**: other | **Why chosen**: fully type-annotated, rich multi-section docstring, sweet-spot length (124 lines)

```python
class Authorization:
    """Represents the parts of an ``Authorization`` request header.

    :attr:`.Request.authorization` returns an instance if the header is set.

    An instance can be used with the test :class:`.Client` request methods' ``auth``
    parameter to send the header in test requests.

    Depending on the auth scheme, either :attr:`parameters` or :attr:`token` will be
    set. The ``Basic`` scheme's token is decoded into the ``username`` and ``password``
    parameters.

    For convenience, ``auth["key"]`` and ``auth.key`` both access the key in the
    :attr:`parameters` dict, along with ``auth.get("key")`` and ``"key" in auth``.

    .. versionchanged:: 2.3
        The ``token`` parameter and attribute was added to support auth schemes that use
        a token instead of parameters, such as ``Bearer``.

    .. versionchanged:: 2.3
        The object is no longer a ``dict``.

    .. versionchanged:: 0.5
        The object is an immutable dict.
    """

    def __init__(
        self,
        auth_type: str,
        data: dict[str, str | None] | None = None,
        token: str | None = None,
    ) -> None:
        self.type = auth_type
        """The authorization scheme, like ``basic``, ``digest``, or ``bearer``."""

        if data is None:
            data = {}

        self.parameters = data
        """A dict of parameters parsed from the header. Either this or :attr:`token`
        will have a value for a given scheme.
        """

        self.token = token
        """A token parsed from the header. Either this or :attr:`parameters` will have a
        value for a given scheme.

        .. versionadded:: 2.3
        """

    def __getattr__(self, name: str) -> str | None:
        return self.parameters.get(name)

    def __getitem__(self, name: str) -> str | None:
        return self.parameters.get(name)

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.parameters.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self.parameters

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Authorization):
            return NotImplemented

        return (
            other.type == self.type
            and other.token == self.token
            and other.parameters == self.parameters
        )

    @classmethod
    def from_header(cls, value: str | None) -> te.Self | None:
        """Parse an ``Authorization`` header value and create an instance of
        this class, or ``None`` if the value is empty.

        :param value: The header value to parse.

        .. versionadded:: 2.3
        """
        if not value:
            return None

        scheme, _, rest = value.partition(" ")
        scheme = scheme.lower()
        rest = rest.strip()

        if scheme == "basic":
            try:
                username, _, password = base64.b64decode(rest).decode().partition(":")
            except (binascii.Error, UnicodeError):
                return None

            return cls(scheme, {"username": username, "password": password})

        if "=" in rest.rstrip("="):
            # = that is not trailing, this is parameters.
            return cls(scheme, parse_dict_header(rest), None)

        # No = or only trailing =, this is a token.
        return cls(scheme, None, rest)

    def to_header(self) -> str:
        """Convert to an ``Authorization`` header value.

        .. versionadded:: 2.0
        """
        if self.type == "basic":
            value = base64.b64encode(
                f"{self.username}:{self.password}".encode()
            ).decode("ascii")
            return f"Basic {value}"

        if self.token is not None:
            return f"{self.type.title()} {self.token}"

        return f"{self.type.title()} {dump_header(self.parameters)}"

    def __str__(self) -> str:
        return self.to_header()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.to_header()}>"
```

## Exemplar 3: `src/werkzeug/middleware/dispatcher.py:44-81` (`DispatcherMiddleware`)

**Layer**: shared | **Role**: other | **Why chosen**: fully type-annotated, rich multi-section docstring, sweet-spot length (38 lines)

```python
class DispatcherMiddleware:
    """Combine multiple applications as a single WSGI application.
    Requests are dispatched to an application based on the path it is
    mounted under.

    :param app: The WSGI application to dispatch to if the request
        doesn't match a mounted path.
    :param mounts: Maps path prefixes to applications for dispatching.
    """

    def __init__(
        self,
        app: WSGIApplication,
        mounts: dict[str, WSGIApplication] | None = None,
    ) -> None:
        self.app = app
        self.mounts = mounts or {}

    def __call__(
        self, environ: WSGIEnvironment, start_response: StartResponse
    ) -> t.Iterable[bytes]:
        script = environ.get("PATH_INFO", "")
        path_info = ""

        while "/" in script:
            if script in self.mounts:
                app = self.mounts[script]
                break

            script, last_item = script.rsplit("/", 1)
            path_info = f"/{last_item}{path_info}"
        else:
            app = self.mounts.get(script, self.app)

        original_script_name = environ.get("SCRIPT_NAME", "")
        environ["SCRIPT_NAME"] = original_script_name + script
        environ["PATH_INFO"] = path_info
        return app(environ, start_response)
```

## Exemplar 4: `src/werkzeug/routing/converters.py:48-82` (`UnicodeConverter`)

**Layer**: shared | **Role**: other | **Why chosen**: fully type-annotated, rich multi-section docstring, sweet-spot length (35 lines)

```python
class UnicodeConverter(BaseConverter):
    """This converter is the default converter and accepts any string but
    only one path segment.  Thus the string can not include a slash.

    This is the default validator.

    Example::

        Rule('/pages/<page>'),
        Rule('/<string(length=2):lang_code>')

    :param map: the :class:`Map`.
    :param minlength: the minimum length of the string.  Must be greater
                      or equal 1.
    :param maxlength: the maximum length of the string.
    :param length: the exact length of the string.
    """

    def __init__(
        self,
        map: Map,
        minlength: int = 1,
        maxlength: int | None = None,
        length: int | None = None,
    ) -> None:
        super().__init__(map)
        if length is not None:
            length_regex = f"{{{int(length)}}}"
        else:
            if maxlength is None:
                maxlength_value = ""
            else:
                maxlength_value = str(int(maxlength))
            length_regex = f"{{{int(minlength)},{maxlength_value}}}"
        self.regex = f"[^/]{length_regex}"
```

## Exemplar 5: `src/werkzeug/exceptions.py:366-399` (`MethodNotAllowed`)

**Layer**: shared | **Role**: other | **Why chosen**: fully type-annotated, rich multi-section docstring, sweet-spot length (34 lines)

```python
class MethodNotAllowed(HTTPException):
    """*405* `Method Not Allowed`

    Raise if the server used a method the resource does not handle.  For
    example `POST` if the resource is view only.  Especially useful for REST.

    The first argument for this exception should be a list of allowed methods.
    Strictly speaking the response would be invalid if you don't provide valid
    methods in the header which you can do with that list.
    """

    code = 405
    description = "The method is not allowed for the requested URL."

    def __init__(
        self,
        valid_methods: t.Iterable[str] | None = None,
        description: str | None = None,
        response: SansIOResponse | None = None,
    ) -> None:
        """Takes an optional list of valid http methods
        starting with werkzeug 0.3 the list will be mandatory."""
        super().__init__(description=description, response=response)
        self.valid_methods = valid_methods

    def get_headers(
        self,
        environ: WSGIEnvironment | None = None,
        scope: dict[str, t.Any] | None = None,
    ) -> list[tuple[str, str]]:
        headers = super().get_headers(environ, scope)
        if self.valid_methods:
            headers.append(("Allow", ", ".join(self.valid_methods)))
        return headers
```

## Exemplar 6: `src/werkzeug/formparser.py:132-312` (`FormDataParser`)

**Layer**: shared | **Role**: other | **Why chosen**: fully type-annotated, rich multi-section docstring, sweet-spot length (181 lines)

```python
class FormDataParser:
    """This class implements parsing of form data for Werkzeug.  By itself
    it can parse multipart and url encoded form data.  It can be subclassed
    and extended but for most mimetypes it is a better idea to use the
    untouched stream and expose it as separate attributes on a request
    object.

    :param stream_factory: An optional callable that returns a new read and
                           writeable file descriptor.  This callable works
                           the same as :meth:`Response._get_file_stream`.
    :param max_form_memory_size: the maximum number of bytes to be accepted for
                           in-memory stored form data.  If the data
                           exceeds the value specified an
                           :exc:`~exceptions.RequestEntityTooLarge`
                           exception is raised.
    :param max_content_length: If this is provided and the transmitted data
                               is longer than this value an
                               :exc:`~exceptions.RequestEntityTooLarge`
                               exception is raised.
    :param silent: If set to False parsing errors will not be caught.
    :param max_form_parts: The maximum number of multipart parts to be parsed. If this
        is exceeded, a :exc:`~exceptions.RequestEntityTooLarge` exception is raised.

    .. versionchanged:: 3.2
        The ``cls`` parameter and attribute are deprecated and will be removed
        in Werkzeug 3.3. They will always be ``ImmutableMultiDict``.

    .. versionchanged:: 3.0
        The ``charset`` and ``errors`` parameters were removed.

    .. versionchanged:: 3.0
        The ``parse_functions`` attribute and ``get_parse_func`` methods were removed.

    .. versionchanged:: 2.2.3
        Added the ``max_form_parts`` parameter.

    .. versionadded:: 0.8
    """

    def __init__(
        self,
        stream_factory: TStreamFactory | None = None,
        max_form_memory_size: int | None = None,
        max_content_length: int | None = None,
        silent: bool = True,
        *,
        max_form_parts: int | None = None,
        **kwargs: t.Any,
    ) -> None:
        if stream_factory is None:
            stream_factory = default_stream_factory

        self.stream_factory = stream_factory
        self.max_form_memory_size = max_form_memory_size
        self.max_content_length = max_content_length
        self.max_form_parts = max_form_parts

        if "cls" in kwargs:
            import warnings

            warnings.warn(
                "The 'cls' parameter is deprecated and will be removed in Werkzeug 3.3."
                " It will always be 'ImmutableMultiDict'.",
                DeprecationWarning,
                stacklevel=2,
            )

        self.cls: type[ImmutableMultiDict[str, t.Any]] | None = kwargs.get("cls")
        self.silent = silent

    def parse_from_environ(self, environ: WSGIEnvironment) -> t_parse_result:
        """Parses the information from the environment as form data.

        :param environ: the WSGI environment to be used for parsing.
        :return: A tuple in the form ``(stream, form, files)``.
        """
        stream = get_input_stream(environ, max_content_length=self.max_content_length)
        content_length = get_content_length(environ)
        mimetype, options = parse_options_header(environ.get("CONTENT_TYPE"))
        return self.parse(
            stream,
            content_length=content_length,
            mimetype=mimetype,
            options=options,
        )

    def parse(
        self,
        stream: t.IO[bytes],
        mimetype: str,
        content_length: int | None,
        options: dict[str, str] | None = None,
    ) -> t_parse_result:
        """Parses the information from the given stream, mimetype,
        content length and mimetype parameters.

        :param stream: an input stream
        :param mimetype: the mimetype of the data
        :param content_length: the content length of the incoming data
        :param options: optional mimetype parameters (used for
                        the multipart boundary for instance)
        :return: A tuple in the form ``(stream, form, files)``.

        .. versionchanged:: 3.0
            The invalid ``application/x-url-encoded`` content type is not
            treated as ``application/x-www-form-urlencoded``.
        """
        if mimetype == "multipart/form-data":
            parse_func = self._parse_multipart
        elif mimetype == "application/x-www-form-urlencoded":
            parse_func = self._parse_urlencoded
        else:
            if self.cls is not None:
                return stream, self.cls(), self.cls()

            return stream, ImmutableMultiDict(), ImmutableMultiDict()

        if options is None:
            options = {}

        try:
            return parse_func(stream, mimetype, content_length, options)
        except ValueError:
            if not self.silent:
                raise

        if self.cls is not None:
            return stream, self.cls(), self.cls()

        return stream, ImmutableMultiDict(), ImmutableMultiDict()

    def _parse_multipart(
        self,
        stream: t.IO[bytes],
        mimetype: str,
        content_length: int | None,
        options: dict[str, str],
    ) -> t_parse_result:
        boundary = options.get("boundary", "").encode("ascii")

        if not boundary:
            raise ValueError("Missing boundary")

        kwargs: dict[str, t.Any] = dict(
            stream_factory=self.stream_factory,
            max_form_memory_size=self.max_form_memory_size,
            max_form_parts=self.max_form_parts,
        )

        if self.cls is not None:
            kwargs["cls"] = self.cls

        with MultiPartParser(**kwargs) as parser:
            form, files = parser.parse(stream, boundary, content_length)

        return stream, form, files

    def _parse_urlencoded(
        self,
        stream: t.IO[bytes],
        mimetype: str,
        content_length: int | None,
        options: dict[str, str],
    ) -> t_parse_result:
        if (
            self.max_form_memory_size is not None
            and content_length is not None
            and content_length > self.max_form_memory_size
        ):
            raise RequestEntityTooLarge()

        items = parse_qsl(
            stream.read().decode(),
            keep_blank_values=True,
            errors="werkzeug.url_quote",
        )

        if self.cls is not None:
            return stream, self.cls(items), self.cls()

        return stream, ImmutableMultiDict(items), ImmutableMultiDict()
```

## Exemplar 7: `src/werkzeug/http.py:262-278` (`unquote_header_value`)

**Layer**: shared | **Role**: other | **Why chosen**: fully type-annotated, rich multi-section docstring, sweet-spot length (17 lines)

```python
def unquote_header_value(value: str) -> str:
    """Remove double quotes and backslash escapes from a header value.

    This is the reverse of :func:`quote_header_value`.

    :param value: The header value to unquote.

    .. versionchanged:: 3.2
        Removes escape preceding any character.

    .. versionchanged:: 3.0
        The ``is_filename`` parameter is removed.
    """
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return _unslash_re.sub(r"\g<1>", value[1:-1])

    return value
```

## Exemplar 8: `src/werkzeug/http.py:1018-1040` (`unquote_etag`)

**Layer**: shared | **Role**: other | **Why chosen**: fully type-annotated, rich multi-section docstring, sweet-spot length (23 lines)

```python
def unquote_etag(
    etag: str | None,
) -> tuple[str, bool] | tuple[None, None]:
    """Unquote a single etag:

    >>> unquote_etag('W/"bar"')
    ('bar', True)
    >>> unquote_etag('"bar"')
    ('bar', False)

    :param etag: the etag identifier to unquote.
    :return: a ``(etag, weak)`` tuple.
    """
    if not etag:
        return None, None
    etag = etag.strip()
    weak = False
    if etag.startswith(("W/", "w/")):
        weak = True
        etag = etag[2:]
    if etag[:1] == etag[-1:] == '"':
        etag = etag[1:-1]
    return etag, weak
```
