set(MODULE_NAME DentoFac)

set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
  DentoFacLib/__init__.py
  DentoFacLib/RuntimeStatus.py
  )

slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  )
