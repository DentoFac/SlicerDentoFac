set(MODULE_NAME DentoFac)

set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
  DentoFacLib/__init__.py
  DentoFacLib/ExtensionStatus.py
  DentoFacLib/RuntimeStatus.py
  DentoFacLib/Dependencies/__init__.py
  DentoFacLib/Dependencies/NNUNet.py
  DentoFacLib/Models/__init__.py
  DentoFacLib/Models/ModelStore.py
  DentoFacLib/Diagnostics/__init__.py
  DentoFacLib/Diagnostics/Collector.py
  Testing/SharedServicesTestCase.py
  )

slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  )
