# Glossary

### Argument
An _argument_ is a string/value proceding a call to a software program on the command-line that will be passed to that program.

### Available
_Available_ refers to a level at which the block is seen in the [catalog](./glossary.md#catalog). A block has available status (A) when the block is within a vendor that is linked to the active workspace. Blocks cannot be used nor opened from this level.

### Backend Tool
In this context, a _backend_ _tool_ is a software program capable of performing a specific task on HDL source files. Some examples are: Quartus, Vivado, and GHDL.

### Block
A legoHDL _block_ is a folder containing HDL source code and any supporting files. Every block has a special [Block.cfg](./glossary.md#blockcfg) metadata file. These are the "packages" that this package manager manages.

Since a block contains the HDL source code, blocks therefore contain HDL [units](./glossary.md#unit).

### Block.cfg
The _Block.cfg_ file is a metadata configuration file that follows similiar syntax to that of an ini file. legoHDL uses this file to mark its directory as a block.

### Block Identifier
A _block_ _identifier_ is a unique case-insensitive title for a block composed of 3 sections: [vendor](./glossary.md#vendor), [library](./glossary.md#library), and name. An identifier's sections are separated by a dot (`.`). The vendor section is optional and can be left blank.

### Blueprint
A _blueprint_ is the outputted text file when a block is exported for building. It mainly consists of [labels](./glossary.md#label) and their respective file paths. 

This file is always created in the `build/` directory found at the root of the current block.

### Catalog
The _catalog_ is the list of searchable blocks within the current active workspace. Blocks can exist at 3 levels within the catalog: [downloaded](./glossary.md#downloaded) (D), [installed](./glossary.md#installed) (I), and/or [available](./glossary.md#available) (A).

### Development Tool
A _development tool_ is a software program specialized for a particular language that automates specific tasks to developing new projects for that language.

### Downloaded
_Downloaded_ refers to a level at which the block is seen in the [catalog](./glossary.md#catalog). A block has download status (D) if the block is within the active workspace's local path. Blocks that are downloaded are said to be in-development. 

Blocks can be used from this level within other blocks only if the `multi-develop` setting is enabled.

### Flag
A _flag_ is a special type of [argument](./glossary.md#argument) that controls or modifies how the specified command will function.

### Hardware Description Languages (HDL)
_Hardware_ _Description_ _Languages_ are a type of specialized computer language to describe electronic circuits.

### Installed
_Installed_ refers to a level at which the block is seen in the [catalog](./glossary.md#catalog). A block has install status (I) when the block is within the active workspace's cache. 

Installed blocks are considered stable and are able to be used within blocks in-development.

### Intellectual Property (IP)
_Intellectual Property_ is a created design. The HDL designs within legoHDL blocks can be considered IP. 

### Label
A _label_ is a unique name given to a group of files defined by their file extension. Defined labels are written to the blueprint file. Every label is evaluated as all upper-case and will have an `@` symbol preceding it.

Special default labels are: 
- `VHDL-SRC`, `VHDL-SIM`, `VHDL-LIB`, `VHDL-SRC-TOP`, `VHDL-SIM-TOP` for VHDL files
- `VLOG-SRC`, `VLOG-SIM`, `VLOG-LIB`, `VLOG-SRC-TOP`, `VLOG-SIM-TOP` for Verilog files

### legohdl.cfg
The _legohdl.cfg_ file contains the system-wide configuration settings for legoHDL.

### Library
A _library_ is the namespace that encapsulates [blocks](./glossary.md#block). When using VHDL entities or packages, this is also those respective library.

### Package Manager
A _package manager_ is a software program used to automate the finding, installing, and uninstalling of modular groups of related files ("packages").

### Partial version
A _partial_ _version_ consists of either 1 or 2 of the most significant parts of a semantic version (version X or version X.X).

### Plugin
A _plugin_ is a custom program to build the current block's design. It can consist of an executable or script written in any language to call any desired tool to perform any task such as linting, simulation, synthesis, generating a bitstream, or programming a bitfile to a target FPGA.

In general, every plugin should read the [blueprint](./glossary.md#blueprint) file to collect necessary data such as the VHDL and Verilog files used for the current design. It is up to the developer to do what they want with the blueprint's collected information.

### Profile
A _profile_ is a folder/repository that is a combination of settings defined in a `legohdl.cfg` file, a template defined in a `template/` folder, and/or a set of plugins defined in a `plugins/` folder. Profiles are used to share or save certain configurations.

### Project
A _project_ is a folder containing HDL source code and any supporting files. The only difference between it and a block is it does not have the special Block.cfg file.

### Semantic Versioning
_Semantic_ _Versioning_ is a popular versioning scheme consisting of 3 different levels of numerical significance: major, minor, and patch.

### Shortcutting
_Shorcutting_ refers to only giving legoHDL partial information about a block's identifier, given that it can logically deduct the rest of the identifier based on what identifier's exist.

### Specific version
A _specific_ _version_ consists of all 3 parts of a semantic version (version X.X.X).

### Unit
A _unit_ is a "piece of hardware" described in HDL. This is called an _entity_ in VHDL and a _module_ in Verilog.

### Vendor
A _vendor_ is the namespace that encapsulates [libraries](./glossary.md#library). Furthermore, a vendor can be a repository that tracks all of the blocks belonging to it by storing their metadata. 

A block does not have to belong to a vendor.

### Verilog
_Verilog_ is a hardware description language used to model and structure digital circuits. It is one of the major languages legoHDL supports.

### VHDL
VHSIC Hardware Description Language, or _VHDL_, is a hardware description langauge used to model and structure digital circuits. It is one of the major languages legoHDL supports.

### Workflow
A _workflow_ is a developer's particular needs and actions required on HDL source files. The typical HDL workflow consists of linting, synthesis, simulation, implementation, generating a bitstream, and programming a bitfile to a target FPGA.

Developers define their own workflow by writing [plugins](./glossary.md#plugin) based on their available tools, environments, and needs.

### Workspaces
_Workspaces_ define what vendors to use and the local path to search under for downloaded blocks. Each workspace has its own cache for block installations, but can share vendors.