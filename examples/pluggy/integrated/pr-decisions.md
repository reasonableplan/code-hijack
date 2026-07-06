# PR Decisions -- what the senior team explicitly rejected or reverted

> Mined from 100 PRs/issues of https://github.com/pytest-dev/pluggy: closed-unmerged proposals, incident reverts, and reviewer preferences
> recorded in GitHub PR/issue history. Rejection and incident decisions
> are cited-evidence-grade -- MUST rules may cite them directly.

## Recurring decision patterns (by occurrence)

1. **instead of** (2 items)
   - "## Summary `subset_hook_caller` fails to exclude plugins that use `specname` to map a differently-named method to a hook"
   - "## Summary `PluginManager.unregister()` fails to clean up the `_name2plugin` mapping for plugins whose truthiness is `Fa"

## Rejected proposals (closed without merge)

- `PR#649` (2026-02-20) **Fix subset_hook_caller failing to exclude plugins using specname**
  matched: `instead of`
  maintainer: "@pytest-dev/core i want to call to action @bysiber should get a public bann due to agentic abuse"
  > ## Summary `subset_hook_caller` fails to exclude plugins that use `specname` to map a differently-named method to a hook. ## Problem The current filtering logic is: ```python plugins_to_remove = {plug for plug in remove_plugins if hasattr(plug, name)} ``` When a plugin registers a hook implementation via `specname`, the actual method on the plugin object has a different name than the hook: ```python class MyPlugin: @hookimpl(specname="my_hook") def some_other_name(self, arg): ... ``` Here, `hasattr(plugin, "my_hook")` returns `False`, so the plugin is incorrectly kept in the subset even though it's in `remove_plugins`. This is used by pytest in conftest scoping via `subset_hook_caller`, so any conftest plugin using `specname` would not be properly excluded when it should be. ## Fix Instead
  Rejected code:
  ```diff
  --- src/pluggy/_manager.py
  @@ -516,7 +516,10 @@ def subset_hook_caller(
           method which manages calls to all registered plugins except the ones
           from remove_plugins."""
           orig: HookCaller = getattr(self.hook, name)
  -        plugins_to_remove = {plug for plug in remove_plugins if hasattr(plug, name)}
  +        registered_plugins = {impl.plugin for impl in orig._hookimpls}
  +        plugins_to_remove = {
  +            plug for plug in remove_plugins if plug in registered_plugins
  +        }
           if plugins_to_remove:
               return _SubsetHookCaller(orig, plugins_to_remove)
           return orig
  ```
- `PR#648` (2026-02-20) **Fix unregister skipping cleanup for falsy plugin objects**
  matched: `instead of`
  maintainer: "this looks like a fully agentic pr without tests, i'm jsut going to close it"
  > ## Summary `PluginManager.unregister()` fails to clean up the `_name2plugin` mapping for plugins whose truthiness is `False`. ## Problem The cleanup check in `unregister()` is: ```python # if self._name2plugin[name] == None registration was blocked: ignore if self._name2plugin.get(name): ``` The comment clarifies the intent: skip only when the value is `None` (which means registration was blocked via `set_blocked`). However, `self._name2plugin.get(name)` evaluates using truthiness, so a plugin object that is falsy (e.g., a container-like plugin where `__len__` returns 0 or `__bool__` returns False) will also be skipped. This leaves a stale entry in `_name2plugin`, which prevents re-registering a plugin with the same name later. ## Fix Use `is not None` instead of truthiness: ```python if s
  Rejected code:
  ```diff
  --- src/pluggy/_manager.py
  @@ -224,7 +224,7 @@ def unregister(
                   hookcaller._remove_plugin(plugin)
   
           # if self._name2plugin[name] == None registration was blocked: ignore
  -        if self._name2plugin.get(name):
  +        if self._name2plugin.get(name) is not None:
               assert name is not None
               del self._name2plugin[name]
   
  ```
