This directory contains information about compiling HSPF including a number of files that can be used to build independent HSPF libraries (not necessarily linked to Python). Here is a brief summary of the contents:

- **HSPF_compilation_documentation.rtf:** documentation on the HSPF source code, the changes made to the code in this distribution, and the other files in the folder (rich text format)
- **HSPF_compilation_documentation.pdf:** documentation on the HSPF source code, the changes made to the code in this distribution, and the other files in the folder (pdf version)
- **depy_conference2015.pdf:** presentation given at the DePy2015 conference on Python applications in data analysis and machine learning
- **compile_hspf.txt:** a batch file provided in text form (.txt) to build an HSPF dynamic link library on Windows
- **compile_libhspf.sh:** a shell script to build an HSPF shared object library on Linux or Unix
- **compile_libhspf.py:** a Python script to download the source data for HSPF, build the HSPF library, build the message file (hspfmsg.wdm) and install PyHSPF
- **make_messagefile.py:** a Python script to build the message file hspfmsg.wdm
- **HSPF13.zip:** modifications to HSPF source code needed to develop independent binaries