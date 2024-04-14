# Sim Data Hub
The sim data hub is developed by the [Methods for Model-based Development in Computational Engineering](https://www.mbd.rwth-aachen.de/) (MBD) 
group at RWTH Aachen University. It is an intermediary platform connecting the data visualization tool GUI_for_data_hubs 
(which will be made public soon) and the scenario-based database. It facilitates the display, interpretation, and export of data.

## Installation
1. Download the zip file or clone the repository:
2. Create a conda environment using ``environment.yml`` and running the following command ``conda env create -f environment.yml``, 
3. Activate the environment with ``conda activate sim_data_hub``.

## Visualization library 
The Sim Data Hub provides essential functions for data visualization through its classes in [`library`](./data_hub/library). 
Two primary classes are offered:
* Regime class: It is the core element of the Data Hub. It enables the management of input data, interpolation of 
tabulated data, and evaluation of mathematical expressions.
* Map class: It offers an overview of the locations where the data was collected through interactive maps generated using
Folium and/or Cartopy. Customized maps can be provided in a tile-structure in `assets/custom_tiles/(Map bodies)`, 
where `Map Bodies` can be Planet (e.g Enceladus, Europa, Ganymede and Mars) or Host rock (e.g claystone, salt and crystalline).
More detailed information can be found in [custommaps.md](custommaps.md).  

The `assets` and `export` folders are specifically designed to support GUI visualization of data:
* `assets`: Provides the basic CSS template for designing the GUI layout.
* `export`: Offers additional features such as data export to NEXD.

## Guideline for Creating a Custom Data Hub
To create a customized data hub, add the Sim Data Hub as a submodule by following these steps:
1. Create a `data_hub` folder within your_data_hub GitHub repository.
2. Navigate to the `data_hub` directory using the command line: `cd data_hub`, and run the following command to add the 
sim_data_hub submodule:
````
git submodule add git@github.com:geo-fluid-dynamics/sim_data_hub.git
````
3. After adding the submodule,the Sim Data Hub will then be included in the `data_hub` directory. However, this folder 
might appear empty. To ensure that the submodule is properly initialized and updated, execute the following commands:
````
git submodule init
git submodule update
````
If the above commands do not work, you can try cloning the submodule recursively using the following command:
````
git clone --recurse-submodules https://github.com/geo-fluid-dynamics/sim_data_hub.git
````

Afterward, add your data to the `data_hub/yaml-db` folder, following the instructions in [`data_hub/yaml-db/readme.md`](./data_hub/yaml-db/readme.md)
for creating YAML files. Additionally, customize the Map and Regime classes to fit your visualization needs. 
An example use case can be found in  [Smart Data Hub](https://github.com/geo-fluid-dynamics/smart_data_hub.git), 
where modified Regime and Map classes are located in `smart_data_hub/data_hub/library`. You can also modify the layout 
of the GUI by copying the assets folder and placing it at the same level as the data_hub folder. The Smart Data Hub is 
an example of creating a custom data hub.  

To connect with the GUI and change the layout to your own design, add a `config_gui.yml` file to your data hub folder 
located at `your_data_hub/data_hub/config_gui.yml`. The contents of this YAML file should include:
```
gui_title: 
logo_data_hub_png: 
logo_data_hub_png_title: 
# additional logo on top right
logo_png:
uni_logo_png: 
main_dropdown_title: 
```
In summary, the structure of your_data_hub should include:
```
-assets (optional)
-data_hub
    -export (optional)
    -library (optional)
    -sim_data_hub
    -yaml-db
    -config_gui.yml (optional)
```
## Credits

The authors of this project are [@CQVera](https://github.com/CQVera) and [@mboxberg](https://github.com/mboxberg).

## License

Distributed under the [MIT License](LICENSE).
