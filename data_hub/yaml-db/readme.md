# yaml-db
This document explains the structure of folders and files in the yaml-db.

## Directories / Folders
Each folder in the yaml-db represents a distinct category from the dropdown list in GUI, each folder contains YAML files.

## Files
Within each folder, there can be multiple YAML files associated with specific datasets.
Each YAML file should include a "name" field, a name similar to the filename, and a "description" field 
offering details about the dataset. Additionally, each file includes various other fields depending on the dataset itself.  

Fields within the YAML files follow a specific structure (it must contain type, value, unit and unit_str; it 
should contain source; other subfields can be omitted):

```
field:
  type: STR                         # String out of [ scalar, array, tabulated, expression, coordinate, string ].
  value: VAL                        # A value of type float, integer, string, array or dictionary.
  dev_pdf: STR                      # Gauss or other parametrized or tabulated PDF.
  dev_value: VAL                    # Hyperparameters of PDF or array with same type as value.
  unit_str: STR                     # Standard string to inidate unit.
  unit: [ 0 0 0 0 0 0 0 ]           # An array of the form [ kg m s K A mol cd ] that gives the unit as the exponent of  
                                    # The SI basis units, e.g., m/s^2 is [ 0 1 -2 0 0 0 0 ].
  variable: STR                     # Function argument (e.g., temperature) (must be used if type is tabulated or 
                                    # expression).
  variable_unit: [ 0 0 0 0 0 0 0 ]  # See above (must be used if type is tabulated or expression).
  variable_unit_str: STR            # Standard string to indicate variable_unit.
  source: STR                       # String with BibTeX key of data source. Free format should not be used here.
  meta_sys: STR                     # Meta data from systematic databases, e.g. NASA database.
  meta_free: STR                    # Free text meta data.
```
An example YAML file can be found at earth/multivariables_equations.yaml.

## sources.bib
The file sources.bib contains BibTeX entries for all sources referenced within the yaml-db.