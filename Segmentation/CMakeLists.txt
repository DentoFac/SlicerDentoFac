set(MODULE_NAME DentoFacSegmentator)

set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
  ${MODULE_NAME}Lib/__init__.py
  ${MODULE_NAME}Lib/ExportManager.py
  ${MODULE_NAME}Lib/DiagnosticsTabAdapter.py
  ${MODULE_NAME}Lib/IconPath.py
  ${MODULE_NAME}Lib/InferenceProgress.py
  ${MODULE_NAME}Lib/InstallationStatus.py
  ${MODULE_NAME}Lib/ModelPath.py
  ${MODULE_NAME}Lib/ModuleSettings.py
  ${MODULE_NAME}Lib/PythonDependencyChecker.py
  ${MODULE_NAME}Lib/SegmentationResultProcessor.py
  ${MODULE_NAME}Lib/SegmentStatisticsReport.py
  ${MODULE_NAME}Lib/SegmentationWidget.py
  ${MODULE_NAME}Lib/Signal.py
  ${MODULE_NAME}Lib/SupportDiagnostics.py
  ${MODULE_NAME}Lib/Utils.py
  Testing/__init__.py
  Testing/_headless_stubs.py
  Testing/DentoFacSegmentatorWidgetTestCase.py
  Testing/ExportManagerTestCase.py
  Testing/InferenceProgressTestCase.py
  Testing/IntegrationTestCase.py
  Testing/ModuleSettingsTestCase.py
  Testing/PythonDependencyCheckerTestCase.py
  Testing/SegmentationResultProcessorTestCase.py
  Testing/SegmentStatisticsReportTestCase.py
  Testing/SegmentationWidgetTestCase.py
  Testing/SupportDiagnosticsTestCase.py
  Testing/Utils.py
  )

set(MODULE_PYTHON_RESOURCES
  Resources/Icons/${MODULE_NAME}.png
  Resources/Icons/${MODULE_NAME}_full_icon.png
  Resources/Icons/dentofac-segmentator.svg
  Resources/Icons/info.png
  Resources/Icons/loading.gif
  Resources/Icons/start_icon.png
  Testing/pytest.ini
  )

slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  RESOURCES ${MODULE_PYTHON_RESOURCES}
  )

if(BUILD_TESTING)
  if(DENTOFAC_TEST_NNUNET_MODULE_PATH)
    if(NOT EXISTS "${DENTOFAC_TEST_NNUNET_MODULE_PATH}/SlicerNNUNet.py")
      message(FATAL_ERROR
        "DENTOFAC_TEST_NNUNET_MODULE_PATH must contain SlicerNNUNet.py: "
        "${DENTOFAC_TEST_NNUNET_MODULE_PATH}")
    endif()

    # SlicerNNUNet is external to this extension, so build its generic module
    # test only when a compatible installed module directory is supplied.
    SlicerMacroConfigureGenericPythonModuleTests("${MODULE_NAME}" _generic_unitest_scripts)
    foreach(script_name ${_generic_unitest_scripts})
      slicer_add_python_unittest(
        SCRIPT ${script_name}
        SLICER_ARGS --no-main-window --disable-cli-modules
          --additional-module-path ${CMAKE_BINARY_DIR}/${Slicer_QTSCRIPTEDMODULES_LIB_DIR}
          --additional-module-path ${DENTOFAC_TEST_NNUNET_MODULE_PATH}
        TESTNAME_PREFIX nomainwindow_
        )
    endforeach()
  else()
    message(STATUS
      "DentoFac Segmentator generic module CTest is disabled: set "
      "DENTOFAC_TEST_NNUNET_MODULE_PATH to a compatible NNUNet scripted-module directory.")
  endif()

  slicer_add_python_unittest(SCRIPT ${MODULE_NAME}.py)
endif()
