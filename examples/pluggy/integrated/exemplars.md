# Senior Exemplars — Match the rhythm of these

> Selected from https://github.com/pytest-dev/pluggy: representative functions/classes that
> demonstrate the codebase's typical structure, type annotation density,
> and docstring style. Match this rhythm when generating new code.

## Exemplar 1: `testing/test_details.py:132-152` (`test_plugin_getattr_raises_errors`)

**Layer**: shared | **Role**: test | **Why chosen**: fully type-annotated, well-documented, sweet-spot length (21 lines)

```python
def test_plugin_getattr_raises_errors() -> None:
    """Pluggy must be able to handle plugins which raise weird exceptions
    when getattr() gets called (#11).
    """

    class DontTouchMe:
        def __getattr__(self, x):
            raise Exception("can't touch me")

    class Module:
        x: DontTouchMe

    module = Module()
    module.x = DontTouchMe()
    with pytest.raises(Exception, match="touch me"):
        module.x.broken

    pm = PluginManager(hookspec.project_name)
    # register() would raise an error
    pm.register(module, "donttouch")
    assert pm.get_plugin("donttouch") is module
```

## Exemplar 2: `src/pluggy/_hooks.py:79-162` (`HookspecMarker`)

**Layer**: shared | **Role**: other | **Why chosen**: fully type-annotated, well-documented, sweet-spot length (84 lines)

```python
class HookspecMarker:
    """Decorator for marking functions as hook specifications.

    Instantiate it with a project_name to get a decorator.
    Calling :meth:`PluginManager.add_hookspecs` later will discover all marked
    functions if the :class:`PluginManager` uses the same project name.
    """

    __slots__ = ("project_name",)

    def __init__(self, project_name: str) -> None:
        self.project_name: Final = project_name

    @overload
    def __call__(
        self,
        function: _F,
        firstresult: bool = False,
        historic: bool = False,
        warn_on_impl: Warning | None = None,
        warn_on_impl_args: Mapping[str, Warning] | None = None,
    ) -> _F: ...

    @overload  # noqa: F811
    def __call__(  # noqa: F811
        self,
        function: None = ...,
        firstresult: bool = ...,
        historic: bool = ...,
        warn_on_impl: Warning | None = ...,
        warn_on_impl_args: Mapping[str, Warning] | None = ...,
    ) -> Callable[[_F], _F]: ...

    def __call__(  # noqa: F811
        self,
        function: _F | None = None,
        firstresult: bool = False,
        historic: bool = False,
        warn_on_impl: Warning | None = None,
        warn_on_impl_args: Mapping[str, Warning] | None = None,
    ) -> _F | Callable[[_F], _F]:
        """If passed a function, directly sets attributes on the function
        which will make it discoverable to :meth:`PluginManager.add_hookspecs`.

        If passed no function, returns a decorator which can be applied to a
        function later using the attributes supplied.

        :param firstresult:
            If ``True``, the 1:N hook call (N being the number of registered
            hook implementation functions) will stop at I<=N when the I'th
            function returns a non-``None`` result. See :ref:`firstresult`.

        :param historic:
            If ``True``, every call to the hook will be memorized and replayed
            on plugins registered after the call was made. See :ref:`historic`.

        :param warn_on_impl:
            If given, every implementation of this hook will trigger the given
            warning. See :ref:`warn_on_impl`.

        :param warn_on_impl_args:
            If given, every implementation of this hook which requests one of
            the arguments in the dict will trigger the corresponding warning.
            See :ref:`warn_on_impl`.

            .. versionadded:: 1.5
        """

        def setattr_hookspec_opts(func: _F) -> _F:
            if historic and firstresult:
                raise ValueError("cannot have a historic firstresult hook")
            opts: HookspecOpts = {
                "firstresult": firstresult,
                "historic": historic,
                "warn_on_impl": warn_on_impl,
                "warn_on_impl_args": warn_on_impl_args,
            }
            setattr(func, self.project_name + "_spec", opts)
            return func

        if function is not None:
            return setattr_hookspec_opts(function)
        else:
            return setattr_hookspec_opts
```

## Exemplar 3: `downstream/run_downstream.py:36-52` (`EnvironmentUv`)

**Layer**: shared | **Role**: other | **Why chosen**: partially typed, 1-line docstring, sweet-spot length (17 lines)

```python
class EnvironmentUv(BaseModel):
    """uv-venv: create venv, install editables + optional groups/packages."""

    model_config = ConfigDict(extra="forbid")

    editables: list[str] = Field(min_length=1)
    groups: list[str] = Field(default_factory=list)
    packages: list[str] = Field(default_factory=list)

    @field_validator("editables")
    @classmethod
    def editables_non_empty_strings(cls, v: list[str]) -> list[str]:
        for i, s in enumerate(v):
            if not s.strip():
                msg = f"editables[{i}] must be a non-empty string"
                raise ValueError(msg)
        return v
```

## Exemplar 4: `testing/test_details.py:155-181` (`test_not_all_arguments_are_provided_issues_a_warning`)

**Layer**: shared | **Role**: test | **Why chosen**: fully type-annotated, well-documented, sweet-spot length (27 lines)

```python
def test_not_all_arguments_are_provided_issues_a_warning(pm: PluginManager) -> None:
    """Calling a hook without providing all arguments specified in
    the hook spec issues a warning."""

    class Spec:
        @hookspec
        def hello(self, arg1, arg2):
            pass  # pragma: no cover

        @hookspec(historic=True)
        def herstory(self, arg1, arg2):
            pass  # pragma: no cover

    pm.add_hookspecs(Spec)

    with pytest.warns(UserWarning, match=r"'arg1', 'arg2'.*cannot be found.*$"):
        pm.hook.hello()
    with pytest.warns(UserWarning, match=r"'arg2'.*cannot be found.*$"):
        pm.hook.hello(arg1=1)
    with pytest.warns(UserWarning, match=r"'arg1'.*cannot be found.*$"):
        pm.hook.hello(arg2=2)

    with pytest.warns(UserWarning, match=r"'arg1', 'arg2'.*cannot be found.*$"):
        pm.hook.hello.call_extra([], kwargs=dict())

    with pytest.warns(UserWarning, match=r"'arg1', 'arg2'.*cannot be found.*$"):
        pm.hook.herstory.call_historic(kwargs=dict())
```

## Exemplar 5: `testing/test_helpers.py:121-132` (`test_varnames_bound_method_from_module_function`)

**Layer**: shared | **Role**: test | **Why chosen**: fully type-annotated, well-documented, sweet-spot length (12 lines)

```python
def test_varnames_bound_method_from_module_function() -> None:
    """A module-level function assigned to a class attribute becomes a bound
    method when accessed on an instance, but its __qualname__ has no dot.
    varnames must still strip the first parameter."""

    def standalone(self, x) -> None:
        pass  # pragma: no cover

    class MyClass:
        method = standalone

    assert varnames(MyClass().method) == (("x",), ())
```

## Exemplar 6: `testing/test_helpers.py:135-146` (`test_varnames_unconventional_first_param_name`)

**Layer**: shared | **Role**: test | **Why chosen**: fully type-annotated, well-documented, sweet-spot length (12 lines)

```python
def test_varnames_unconventional_first_param_name() -> None:
    """Bound methods strip unconditionally, but unbound methods with
    non-standard first parameter names preserve all arguments."""

    class MyClass:
        def method(this, x) -> None:
            pass  # pragma: no cover

    # Bound: stripped regardless of name.
    assert varnames(MyClass().method) == (("x",), ())
    # Unbound with dotted qualname but non-implicit name: NOT stripped.
    assert varnames(MyClass.method) == (("this", "x"), ())
```

## Exemplar 7: `testing/test_hookcaller.py:340-365` (`test_hookrelay_registry`)

**Layer**: shared | **Role**: test | **Why chosen**: fully type-annotated, well-documented, sweet-spot length (26 lines)

```python
def test_hookrelay_registry(pm: PluginManager) -> None:
    """Verify hook caller instances are registered by name onto the relay
    and can be likewise unregistered."""

    class Api:
        @hookspec
        def hello(self, arg: object) -> None:
            "api hook 1"

    pm.add_hookspecs(Api)
    hook = pm.hook
    assert hasattr(hook, "hello")
    assert repr(hook.hello).find("hello") != -1

    class Plugin:
        @hookimpl
        def hello(self, arg):
            return arg + 1

    plugin = Plugin()
    pm.register(plugin)
    out = hook.hello(arg=3)
    assert out == [4]
    assert not hasattr(hook, "world")
    pm.unregister(plugin)
    assert hook.hello(arg=3) == []
```

## Exemplar 8: `testing/test_hookcaller.py:368-390` (`test_hookrelay_registration_by_specname`)

**Layer**: shared | **Role**: test | **Why chosen**: fully type-annotated, well-documented, sweet-spot length (23 lines)

```python
def test_hookrelay_registration_by_specname(pm: PluginManager) -> None:
    """Verify hook caller instances may also be registered by specifying a
    specname option to the hookimpl"""

    class Api:
        @hookspec
        def hello(self, arg: object) -> None:
            "api hook 1"

    pm.add_hookspecs(Api)
    hook = pm.hook
    assert hasattr(hook, "hello")
    assert len(pm.hook.hello.get_hookimpls()) == 0

    class Plugin:
        @hookimpl(specname="hello")
        def foo(self, arg: int) -> int:
            return arg + 1

    plugin = Plugin()
    pm.register(plugin)
    out = hook.hello(arg=3)
    assert out == [4]
```
