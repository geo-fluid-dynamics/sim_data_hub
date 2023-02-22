# importing libraries
import ast
import base64
import copy
import os

import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, dash_table, State
from dash.exceptions import PreventUpdate
from flask import abort, send_from_directory
from plotly.tools import mpl_to_plotly

import yaml
import importlib

module_str = ''
module = None
modules = (os.path.normpath(os.path.split(os.getcwd())[0])).split(os.sep)
for i in range(1, len(modules) + 1):
    try:
        importlib.import_module(modules[-i])
        module_str = modules[-i] + '.' + module_str
        module = modules[-i]
        break
    except (ModuleNotFoundError, ValueError) as error:
        module_str = modules[-i] + '.' + module_str

if module is None:  # no submodules
    module_str = ''
    module = 'sim-data-hub'


def load_lib_path(map_lib_path: str = module_str + 'sim-data-hub.library.map.Map',
                  regime_lib_path: str = module_str + 'sim-data-hub.library.regimes.Regime',
                  yaml_loader_path: str = module_str + 'sim-data-hub.library.regimes.Regime',
                  export_lib_path: str = module_str + 'sim-data-hub.export',
                  source_path: str = os.path.join('..', 'yaml-db'),
                  assets_path: str = 'assets',
                  client_relpath: str = os.path.join('assets', 'client'),
                  stylesheet_path: str = 'stylesheet.css'):
    global Map, Regime, PrettySafeLoader, export, yaml_path, assets_folder_path, external_stylesheet, client_path, server_route

    try:  # using sim-data-hub as submodule
        importlib.import_module(module)

    except ModuleNotFoundError:
        map_lib_path = 'library.map.Map'
        regime_lib_path = 'library.regimes.Regime'
        yaml_loader_path = 'library.regimes.Regime'
        export_lib_path = 'export'
        source_path = 'yaml-db'

    Map = getattr(importlib.import_module(map_lib_path), 'Map')
    Regime = getattr(importlib.import_module(regime_lib_path), 'Regime')
    PrettySafeLoader = getattr(importlib.import_module(yaml_loader_path), 'PrettySafeLoader')
    export = importlib.import_module(export_lib_path)
    yaml_path = source_path
    assets_folder_path = os.path.join(os.getcwd(), assets_path)
    # path for temporary downloadable files
    client_path = client_relpath
    external_stylesheet = [stylesheet_path]
    server_route = os.path.join(os.path.relpath(os.getcwd(), os.path.dirname(__file__)),
                                client_path)


load_lib_path()


def load_available_yaml_files(current_regimes: dict, deep_update: bool = False):
    """
    Function to update the dictionary of available yaml files / regimes. This only detects new files or removed files if
    deep_update = False. If deep_update = True it detects external changes in yaml-files, too.
    :param current_regimes: currently available regimes that need to be updated
    :param deep_update: Detect external changes in yaml-files? Default: False
    :return: updated available regimes
    """
    global deep_update_necessary

    # Check if any component has set a forced deep_update
    if deep_update_necessary:
        deep_update = True
        deep_update_necessary = False

    # make a shallow copy of the input
    available_regimes = dict(current_regimes)
    # Load available yaml files
    for i, (root, dirs, filenames) in enumerate(
            os.walk(os.path.join(os.path.realpath(os.path.dirname(__file__)), os.pardir, yaml_path))):
        if i > 0:  # skip root yaml-db directory
            region = os.path.split(root)[-1]
            if region[0] == '_' or region[0] == '.':
                # skip all "hidden" folders
                continue

            # Add map name if it is not yet available
            if region not in available_regimes.keys():
                available_regimes[region] = dict()

            # Remove files that are not available anymore
            current_files = list(available_regimes[region].keys())
            for filename in current_files:
                if filename not in filenames:
                    del available_regimes[region][filename]

            # Load new files
            for filename in filenames:
                if deep_update or filename not in available_regimes[region].keys():
                    r = Regime()
                    address = os.path.join(os.path.realpath(os.path.dirname(__file__)), os.pardir, yaml_path, region,
                                           filename)
                    r.load_props(address)
                    props = r.props
                    available_regimes[region][filename] = {'regime': r, 'props': props.applymap(str)}
    return available_regimes


def check_changes(data_description, data_name, data_table):
    name_changed = saved_data_state['name'] != data_name
    description_changed = saved_data_state['description'] != data_description
    figures_changed = saved_data_state['figures'] != current_figures
    table_changed = saved_data_state['table_data'] != data_table
    # if any of these conditions is true, then there is unsaved data
    data_changed = name_changed or description_changed or figures_changed or table_changed
    return data_changed


def get_regime_from_current_dataset(data, title, description, figures):
    new_regime = Regime(name=title)
    formated_data = {}
    new_regime.description = description
    new_regime.figures = figures
    # changing the format of the data that will be accepted by our code when saved as yaml file
    for j in range(len(data)):
        prop = data[j].pop('property')
        formated_data[prop] = data[j]
        for entry in formated_data[prop].keys():
            if formated_data[prop][entry] == 'nan':
                formated_data[prop][entry] = None
            if entry in ['value', 'dev_value']:
                current_entry = formated_data[prop][entry]
                if formated_data[prop]['type'] == 'scalar':
                    if current_entry == 'None':
                        current_entry = None
                    if entry in formated_data[prop].keys() and current_entry != '' and current_entry is not None:
                        formated_data[prop][entry] = float(current_entry)
                elif formated_data[prop]['type'] in ['tabulated', 'array']:
                    if entry in formated_data[prop].keys() and current_entry is not None:
                        formated_data[prop][entry] = ast.literal_eval(current_entry)

    # changing the type of the location key from string to dictionary (for locating the boreholes)
    if 'location' in formated_data.keys():
        formated_data['location']['value'] = ast.literal_eval(formated_data['location']['value'])
    new_regime.props = formated_data
    return new_regime


# General settings:
predefined_column_order = ['type', 'value', 'dev_pdf', 'dev_value', 'unit_str', 'unit', 'variable', 'variable_unit',
                           'variable_unit_str', 'source', 'meta_sys', 'meta_free']
dropdown_in_table = ['type']

offline = False

check_fired_by = 'yaml_list_data'
saved_data_state = {'region': None, 'file': None, 'name': None, 'description': None, 'table_data': None,
                    'new_file': False, 'figures': {}}
deep_update_necessary = False
current_figures = {}

# Basic table style:
basic_style_data_conditional = []
# Even rows have a grey background
basic_style_data_conditional.extend([{'if': {'row_index': 'even'}, 'backgroundColor': 'var(--EvenRow)'}])
basic_style_data_conditional.extend(
    [{'if': {'state': 'active'}, 'backgroundColor': 'var(--ActiveEvenRow)',
      'border': '1px solid var(--ActiveEvenRow)'}])

# default html elements to be able to reset them
div_plot_empty = html.Div(id='graph_plot')

# set map path
map_path = 'assets'

# initial load of available files
regimes = load_available_yaml_files({}, deep_update=True)

# Starting Dash GUI
app = dash.Dash(__name__, assets_folder=assets_folder_path, external_stylesheets=external_stylesheet)


def setup_html_gui(gui_title, logo_data_hub_png, logo_data_hub_png_title, logo_png, uni_logo_png,
                   main_dropdown_title):
    global app

    app.title = gui_title

    # this is the whole dash layout of the data-hub
    # starting with main section of the layout
    app.layout = html.Div(children=[
        # INVISIBLE PARTS OF THE LAYOUT
        # this is the confim dialog to replace the existing file
        dcc.ConfirmDialog(id='save_dialog'),
        # Notification that is shown if the chosen filename already exists.
        dcc.ConfirmDialog(id='save_as_dialog'),
        # Notification that is shown if the chosen filename already exists.
        dcc.ConfirmDialog(id='newfile_dialog'),
        # Notification that is shown if a file shall be uploaded.
        dcc.ConfirmDialog(id='upload_dialog'),
        dcc.ConfirmDialog(id='upload_rejected_dialog'),
        # Notification that is shown if a file should be deleted
        dcc.ConfirmDialog(id='delete_dialog'),
        # Notification that is shown if the data was changed but not saved
        dcc.ConfirmDialog(id='data_changed_dialog_region',
                          message='Warning! Data has been changed and will be lost if changing Maps!'),
        dcc.ConfirmDialog(id='data_changed_dialog_datasets',
                          message='Warning! Data has been changed and will be lost if changing dataset!'),

        # START OF THE VISIBLE LAYOUT
        # top div for the heading and logos
        html.Div(className='div_heading_logo', children=[
            # sub div for the "Data Hub" Heading
            html.Div(className='div_heading', children=[
                html.Img(className='logo_left', src=app.get_asset_url(logo_data_hub_png),
                         title=logo_data_hub_png_title),
                # html.Div(className='h1_heading', children='Data Hub')
            ]),
            # sub div for the logos
            html.Div(className='div_logo', children=[
                html.Img(className='logo_right', src=app.get_asset_url(uni_logo_png)) if uni_logo_png else None,
                html.Img(className='logo_right', src=app.get_asset_url(logo_png)) if logo_png else None,
            ])
        ]),

        # this is the box section of the first box which is on the left side named box 1
        html.Div(
            className='div_dropdown',
            children=[
                # this is the section of box inside the first box
                # this contains the dropdowns for the selection of the yaml files
                # the main drop down that select the sub dropdowns
                html.H2(children=main_dropdown_title),
                # this is the main dropdown for the regimes
                dcc.Dropdown(id='main_dropdown', clearable=False, value=list(regimes.keys())[0],
                             options=[{'label': name.title(), 'value': name} for name in list(regimes.keys())]),
                # Heading showing "Datasets"
                html.H2(children='Datasets:'),
                # this div contains the dark blue scorlling area with the select options
                html.Div(className='div_filter_option', children=[
                    # the text area for filtering
                    dcc.Input(className='input_filter', id='input_filter', placeholder='Search for ...', value=''),
                    # this is the add button for creating an empty file
                    html.Button(className='button_filter', children='Filter / Refresh', id='btn_filter', n_clicks=0),
                ]),
                html.Div(className='div_select_area', children=[
                    # div that contains the filter text area and filter button
                    # small left portion div on the left side
                    html.Div(className='div_show_data', children=[
                        # vertical title of "show data"
                        html.P(className='p_show_data', children='Show data'),
                        # radio item select options (circular options)
                        dcc.RadioItems(id='yaml_list_data'),
                    ]),
                    # large right portion div on the left side
                    html.Div(className='div_show_map', children=[
                        # vertical title of "show in map"
                        html.P(className='p_show_map', children='Show in map'),
                        # Checklist select options (square boxes)
                        dcc.Checklist(className='radio', id='yaml_list_map',
                                      labelStyle={'display': 'block', 'white-space': 'nowrap'}),
                    ])
                ]),
                # div for the text area and Add Buttion for the "add/update file", feature
                html.Div(className='div_new_file', children=[
                    dcc.Upload(id='upload_file', children=['Drag and Drop or ', html.A('Select'), ' a File to Upload'],
                               style={'width': 'calc(100% - 6px', 'height': '25px', 'lineHeight': '25px',
                                      'borderWidth': '1px', 'borderStyle': 'dashed', 'borderRadius': '5px',
                                      'borderColor': 'var(--UpdateBorder)', 'textAlign': 'center', 'margin': '2px'}),
                    # text are where the name of the new file or updating previous file will be added
                    dcc.Input(className='input_add_file', id='input_add_file',
                              placeholder='Enter name of new file (*.yaml)', value=''),
                    # this is the add button for creating an empty file
                    html.Button(className='button_add_file', children='Add New File', id='btn_add_file', n_clicks=0)
                ])
            ]),
        # this is the div that contains the whole tab
        html.Div(className='display_map_data_graph', children=[
            # the main tab which contains all the other tabs
            dcc.Tabs(id='tabs_container', children=[
                # first sub tab that apears by _default this is the large map display tap
                dcc.Tab(label='Overview Map', id='tab_map', className='tab', children=[
                    # div that contains the large map
                    html.Div(className='div_single_tab', children=[
                        # large maps
                        html.Iframe(id='html_map', className='iframe_map')
                    ])
                ]),
                # data tab which is for mainly for datatable display
                dcc.Tab(label='Data', id='tab_data', className='tab', children=[
                    # div that contains all the contents of  data tab
                    html.Div(className='div_single_tab', children=[
                        # div that contains the combination of single small map dive, title and description div for data
                        # tab
                        html.Div(className='div_single_tab_map_text', children=[
                            # div for only the single small map for data tab
                            html.Div(id='single_map', className='div_single_map', children=[
                                # single small map
                                html.Iframe(id='html_single_map', className='iframe_map_single')
                            ]),
                            # div for title and description for data tab
                            html.Div(id='single_description', className='div_description', children=[
                                # text area for title for data tab
                                dcc.Textarea(className='textarea_title', id='textarea_title', rows=1, value=[]),
                                # text area for description for data tab
                                dcc.Textarea(className='textarea_description', id='textarea_description', value=[],
                                             spellCheck='true'),
                                html.Div(className='div_figures', id='div_figures', children=[
                                    dbc.Modal(id='modal_figures', centered=True, scrollable=True, size='lg', children=[
                                        dbc.ModalHeader(id='modal_figures_header', children='Figure'),
                                        dbc.ModalBody(id='modal_figures_body', children=[
                                            html.Img(className='img_modal', id='modal_figures_body_img', src=''),
                                            dcc.Textarea(id='modal_figures_body_text', className='textarea_img_modal',
                                                         value='')
                                        ]),
                                        dbc.ModalFooter(id='modal_figures_footer', children=[
                                            html.Form(id='frm_download', method='get',
                                                      children=[html.Button(type='submit', children=['Download'])]),
                                            dbc.Button('Delete', id='btn_delete_img', className='btn_delete'),
                                            dbc.Button('Close', id='btn_close_figure')
                                        ]),
                                    ]),
                                    html.Img(className='img_figure_hidden', id='img_figure_1', src=''),
                                    html.Img(className='img_figure_hidden', id='img_figure_2', src=''),
                                    html.Img(className='img_figure_hidden', id='img_figure_3', src=''),
                                    html.Img(className='img_figure_hidden', id='img_figure_4', src=''),
                                    html.Div(className='div_upload_figure_inline', id='div_upload_figure', children=[
                                        dcc.Upload(className='upload_figure', id='upload_figure', children=[
                                            html.Div(className='div_add_figure', children='+', title='Add a figure')
                                        ])
                                    ])
                                ])
                            ])
                        ]),
                        # div for the main data table in the center for data tab
                        html.Div(id='scrolling_datatable', className='div_main_datatable', children=[
                            dash_table.DataTable(
                                id='data_table',
                                # for exporting the dash data table as CSV file
                                #  export_format='csv',
                                # making the data table editable
                                editable=True,
                                # allow the data column table to be renamed
                                # renamable=True,
                                # making the data table having display afters filters
                                filter_action='native',
                                # enables data to be sorted per-column by user or not ('none')
                                sort_action='native',
                                # sort across 'multi' for more than one or 'single' columns
                                sort_mode='multi',
                                # to select more than one or 'single' columns
                                #  column_selectable='multi',
                                # to select more than one or single rows
                                #  row_selectable='multi',
                                # choose if user can delete a row  or not
                                row_deletable=True,
                                # ids of columns that user selects
                                selected_columns=[],
                                # indices of rows that user selects
                                selected_rows=[],
                                # all data is passed to the table up-front or not ('none')
                                page_action='native',
                                # page number that user is on
                                page_current=0,
                                # number of rows visible per page
                                page_size=1000,
                                style_cell={'overflow': 'hidden', 'textOverflow': 'ellipsis', 'maxWidth': 100},
                                style_data_conditional=basic_style_data_conditional,
                                style_header={'backgroundColor': 'var(--RowHeader)', 'fontWeight': 'bold'},
                                style_header_conditional=[{'if': {'column_id': col}, 'textDecoration': 'underline',
                                                           'textDecorationStyle': 'dotted', } for col in
                                                          ['unit', 'variable_unit']],
                                dropdown={'type': {'options': [{'label': opt, 'value': opt} for opt in
                                                               ['scalar', 'array', 'tabulated', 'expression',
                                                                'coordinate', 'string']]}},
                                tooltip_delay=350,
                                tooltip_duration=None,
                                # Style headers with a dotted underline to indicate a tooltip
                                tooltip_header={'unit': '[ kg m s K A mol cd ]',
                                                'variable_unit': '[ kg m s K A mol cd ]'},
                                css=[{'selector': '.dash-table-tooltip',
                                      'rule': 'font-family: monospace; min-width: 180px; max-width: 180px;'}]
                            )
                        ]),
                        # div for the buttons for data tab
                        html.Div(className='div_buttons', children=[
                            html.Div(children=[
                                dcc.Input(className='input_11a', id='input_add_column', value='', list='column_options',
                                          placeholder='Enter column name...'),
                                html.Datalist(id='column_options', children=[
                                    html.Option(value=col) for col in predefined_column_order
                                ])
                            ]),
                            html.Div(html.Button(className='button_11b', children='Add a column', id='btn_add_column',
                                                 n_clicks=0)),
                            html.Div(html.Button(className='button_12', children='Add a row', id='btn_add_row',
                                                 n_clicks=0)),
                            html.Div(children=[
                                html.Button(className='button_13', children='Save file', id='btn_save_file',
                                            n_clicks=0),
                                html.Div(id='invisible_saved', style={'display': 'none'})
                            ]),
                            html.Div(
                                html.Button(className='button_14a', children='Save file as ...', id='btn_save_file_as',
                                            n_clicks=0)),
                            html.Div(dcc.Input(className='input_14b', id='input_save_file_as', value='',
                                               placeholder='... (*.yaml)')),
                            html.Div(children=[
                                dbc.Modal(id='modal_export', centered=True, scrollable=True, size='lg', children=[
                                    dbc.ModalHeader(id='modal_export_header', children='Export data'),
                                    dbc.ModalBody(id='modal_export_body', children=[
                                        html.Div(children=[
                                            html.H4('Plain YAML'),
                                            html.P('This creates a plain yaml file as it is stored in the database.'),
                                            html.Button(className='btn_exp', id='btn_serve_yaml',
                                                        children='Prepare File'),
                                            html.Form(className='btn_exp', id='frm_download_yaml', method='get',
                                                      children=[
                                                          html.Button(id='btn_frm_download_yaml', type='submit',
                                                                      disabled=True,
                                                                      children='Download')
                                                      ])
                                        ]),
                                        html.Hr(),
                                        html.Div(children=[
                                            html.H4('Ice X (smart_cryobot)'),
                                            html.P('''
                                                    This creates a yaml file with all properties needed for melting probe 
                                                    trajectory modelling. If the current dataset does not contain all 
                                                    necessary properties, they are taken from the default database.
                                                   '''),
                                            html.P(className='p_error', id='p_error_icex', children=''),
                                            html.Button(className='btn_exp', id='btn_serve_icex',
                                                        children='Prepare File'),
                                            html.Form(className='btn_exp', id='frm_download_icex', method='get',
                                                      children=[
                                                          html.Button(id='btn_frm_download_icex', type='submit',
                                                                      disabled=True,
                                                                      children='Download')
                                                      ])
                                        ]),
                                        html.Hr(),
                                        html.Div(children=[
                                            html.H4('NEXD'),
                                            html.P('''
                                                This creates an input file for the seismic wave propagation code NEXD.
                                               '''),
                                            dcc.RadioItems(inputClassName='radio_nexd', id='radio_nexd',
                                                           options=[
                                                               {'label': 'elastic/viscoelastic', 'value': 'elastic'},
                                                               {'label': 'poroelastic (one fluid / saturated)',
                                                                'value': 'poro1f'},
                                                               {'label': 'poroelastic (two fluids / unsaturated)',
                                                                'value': 'poro2f'}],
                                                           value='elastic'),
                                            html.P(className='p_error', id='p_error_nexd', children=''),
                                            html.Button(className='btn_exp', id='btn_serve_nexd',
                                                        children='Prepare File'),
                                            html.Form(className='btn_exp', id='frm_download_nexd', method='get',
                                                      children=[
                                                          html.Button(id='btn_frm_download_nexd', type='submit',
                                                                      disabled=True,
                                                                      children='Download')
                                                      ])
                                        ]),
                                    ]),
                                    dbc.ModalFooter(id='modal_export_footer', children=[
                                        dbc.Button('Close', id='btn_close_export')
                                    ]),
                                ]),
                                html.Button(className='button_21', children='Export data', id='btn_export', n_clicks=0)
                            ]),
                            html.Div(html.Button(className='button_24', children='Delete file', id='btn_delete_file',
                                                 n_clicks=0)),
                        ])
                    ])
                ]),
                # 3rd tab for the ploting routines
                dcc.Tab(label='Plot', id='tab_plot', className='tab', children=[
                    # div for whole tab
                    html.Div(className='div_single_tab', children=[
                        # div that contains the combination of single small map dive, title and description div for
                        # ploting tab
                        html.Div(className='div_single_tab_map_text', children=[
                            # div for the single small maps for ploting tab
                            html.Div(id='single_map_plot', className='div_single_map', children=[
                                # single small map for ploting tab
                                html.Iframe(id='html_single_map_plot', className='iframe_map_single')
                            ]),
                            # div containing text area for title and description for ploting tab
                            html.Div(id='single_description_plot', className='div_description', children=[
                                # text area of title for plot tab
                                dcc.Textarea(id='textarea_title_plot', className='textarea_title', rows=1, value=[],
                                             disabled=True),
                                # text area of description for plot tab
                                dcc.Textarea(id='textarea_description_plot', className='textarea_description', value=[],
                                             disabled=True),
                                html.Div(className='div_figures', id='div_figures_plot', children=[
                                    dbc.Modal(id='modal_figures_plot', centered=True, scrollable=True, size='lg',
                                              children=[
                                                  dbc.ModalHeader(id='modal_figures_header_plot', children='Figure'),
                                                  dbc.ModalBody(id='modal_figures_body_plot', children=[
                                                      html.Img(id='modal_figures_body_img_plot', className='img_modal',
                                                               src=''),
                                                      dcc.Textarea(id='modal_figures_body_text_plot', disabled=True,
                                                                   className='textarea_img_modal')
                                                  ]),
                                                  dbc.ModalFooter(id='modal_figures_footer_plot', children=[
                                                      html.Form(id='frm_download_plot', method='get', children=[
                                                          html.Button(type='submit', children=['Download'])
                                                      ]),
                                                      dbc.Button(id='btn_close_figure_plot', children='Close')
                                                  ])
                                              ]),
                                    html.Img(id='img_figure_1_plot', className='img_figure_hidden', src=''),
                                    html.Img(id='img_figure_2_plot', className='img_figure_hidden', src=''),
                                    html.Img(id='img_figure_3_plot', className='img_figure_hidden', src=''),
                                    html.Img(id='img_figure_4_plot', className='img_figure_hidden', src=''),
                                ])
                            ])
                        ]),
                        # center div for plot tab containing dropdown, input
                        html.Div(className='div_buttons', children=[
                            # The memory store reverts to the default on every page refresh
                            dcc.Store(id='btn_memory'),
                            dcc.ConfirmDialog(id='plot_rejected_dialog'),
                            dcc.ConfirmDialog(id='store_rejected_dialog'),
                            # placeholder
                            html.Div(style={'width': '0.1%', 'display': 'inline-block'}),
                            html.Div(className='dd_plot', children=[
                                dcc.Dropdown(id='graph_dropdown', clearable=False, placeholder='Select property...')]),
                            html.Div(className='dd_plot', children=[
                                dcc.Dropdown(id='graph-multivariables', placeholder='Select one or two variable(s)...',
                                             multi=True)]),
                            html.Div(className='dd_plot', children=[
                                dcc.Dropdown(id='graph-singlevariable', placeholder='Select variable for storing value('
                                                                                    's)...')]),

                            dcc.Input(id='graph_min_x', placeholder='Enter minimum', disabled=True),
                            dcc.Input(id='graph_max_x', placeholder='Enter maximum', disabled=True),
                            dcc.Input(id='graph_constant_x', placeholder='Enter constant value', disabled=True),
                            html.Button(id='btn_store', n_clicks=0, disabled=True, children='Store values'),
                            html.Button(id='btn_plot', n_clicks=0, disabled=True, children='Plot property')

                        ]),

                        html.Div(id='div_plot', className='div_main_datatable', children=div_plot_empty)
                    ])
                ])
            ])
        ])
    ])


# server route to all downloadable files
@app.server.route(os.path.join('/', server_route, '<path:filename>'))
def serve_image(filename):
    try:
        return send_from_directory(client_path, path=filename, as_attachment=True)
    except FileNotFoundError:
        abort(404)


# back end for the graphical user interface starts from here
# dropdowns
@app.callback([Output('yaml_list_map', 'options'),
               Output('yaml_list_map', 'value'),
               Output('yaml_list_data', 'options'),
               Output('yaml_list_data', 'value')],
              [Input('btn_filter', 'n_clicks'),
               Input('data_changed_dialog_datasets', 'cancel_n_clicks'),
               Input('data_changed_dialog_region', 'submit_n_clicks')],
              [State('main_dropdown', 'value'),
               State('input_filter', 'value'),
               State('yaml_list_map', 'value'),
               State('yaml_list_data', 'value')])
def update_yaml_list(filter_n_clicks, _data_changed_datasets_cancel_n_clicks, _data_changed_region_submit_n_clicks,
                     region, filter_value, list_map_selected_prev, data_selected_prev):
    global regimes

    source = None
    # determine which Input has fired
    ctx = dash.callback_context
    if ctx.triggered:
        source = ctx.triggered[0]['prop_id'].split('.')[0]

    if source == 'data_changed_dialog_datasets':
        return dash.no_update, dash.no_update, dash.no_update, saved_data_state['file']

    if filter_n_clicks:
        # update available files first
        regimes = load_available_yaml_files(regimes)

    filelist = list(regimes[region].keys())
    map_items = []
    data_items = []
    names = {}
    # iterate through all files and get names from Regime objects
    for filename in filelist:
        name = regimes[region][filename]['regime'].name
        if name == regimes[region][filename]['regime'].NAME_DEFAULT:
            # if the name of the Regime object is 'Default' use filename
            name = filename
        names[filename] = name

    # sort list by name
    for filename in [filenames[0] for filenames in sorted(names.items(), key=lambda x: x[1])]:
        # the label will be the name of the Regime object, but the value will always be the filename
        enabled = regimes[region][filename]['regime'].props.__contains__('location')
        if names[filename].lower().find(filter_value.lower()) >= 0:
            map_items.append({'label': names[filename], 'value': filename, 'disabled': not enabled})
            data_items.append({'label': '', 'value': filename})

    # Keep previously selected items if possible (i.e., not deleted)
    if list_map_selected_prev is not None:
        list_map_selected = list(set(names).intersection(set(list_map_selected_prev)))
    else:
        list_map_selected = []

    if source == 'data_changed_dialog_region':
        data_selected = sorted(names)[0]
    elif saved_data_state['file'] is not None:
        data_selected = saved_data_state['file']
    elif data_selected_prev and data_selected_prev in names:
        data_selected = data_selected_prev
    else:
        data_selected = sorted(names)[0]

    saved_data_state['region'] = copy.deepcopy(region)
    saved_data_state['file'] = None

    return map_items, list_map_selected, data_items, data_selected


@app.callback(Output('main_dropdown', 'value'),
              Input('data_changed_dialog_region', 'cancel_n_clicks'),
              prevent_initial_call=True)
def reset_selected_region(_data_changed_region_cancel_n_clicks):
    return saved_data_state['region']


# check if state of data has changed and ask to save
@app.callback([Output('data_changed_dialog_region', 'displayed'),
               Output('data_changed_dialog_region', 'submit_n_clicks')],
              Input('main_dropdown', 'value'),
              [State('textarea_title', 'value'),
               State('textarea_description', 'value'),
               State('data_table', 'data'),
               State('data_changed_dialog_region', 'submit_n_clicks')],
              prevent_initial_call=True)
def data_changed_check_region(_selected_region, data_name, data_description, data_table, n_approved_changes):
    global check_fired_by

    if check_fired_by == 'main_dropdown':
        check_fired_by = None
        raise PreventUpdate
    else:
        check_fired_by = 'main_dropdown'

    if saved_data_state['region'] is None:
        # initial call
        return False, 1
    data_changed = check_changes(data_description, data_name, data_table)
    if data_changed:
        return data_changed, dash.no_update
    else:
        return data_changed, n_approved_changes + 1 if n_approved_changes is not None else 1


@app.callback([Output('data_changed_dialog_datasets', 'displayed'),
               Output('data_changed_dialog_datasets', 'submit_n_clicks')],
              [Input('yaml_list_data', 'value'),
               Input('btn_add_file', 'n_clicks'),
               Input('upload_file', 'contents')],
              [State('textarea_title', 'value'),
               State('textarea_description', 'value'),
               State('data_table', 'data'),
               State('data_changed_dialog_datasets', 'submit_n_clicks')])
def data_changed_check_datasets(selected_file, _n_clicks_new, file_content, data_name, data_description, data_table,
                                n_approved_changes):
    global check_fired_by

    # determine which Input has fired
    ctx = dash.callback_context
    if ctx.triggered:
        check_fired_by = ctx.triggered[0]['prop_id'].split('.')[0]

    if check_fired_by == 'yaml_list_data':
        if saved_data_state['file'] is None:
            # initial call or last action was to delete a file
            return False, 1
        elif saved_data_state['file'] == selected_file:
            if saved_data_state['new_file']:
                return False, n_approved_changes + 1 if n_approved_changes is not None else 1
            else:
                # to catch the reset of the radio item
                return False, dash.no_update
    elif check_fired_by == 'upload_file':
        if file_content == '':
            return False, dash.no_update
    data_changed = check_changes(data_description, data_name, data_table)
    # if there is no unsaved data, increase the number of approvements to call the update of the data
    if data_changed:
        return data_changed, dash.no_update
    else:
        return data_changed, n_approved_changes + 1


@app.callback([Output('div_plot', 'children'),
               Output('textarea_title_plot', 'value'),
               Output('textarea_title_plot', 'title'),
               Output('textarea_description_plot', 'value'),
               Output('html_single_map_plot', 'srcDoc'),
               Output('img_figure_1_plot', 'src'),
               Output('img_figure_2_plot', 'src'),
               Output('img_figure_3_plot', 'src'),
               Output('img_figure_4_plot', 'src'),
               Output('img_figure_1_plot', 'className'),
               Output('img_figure_2_plot', 'className'),
               Output('img_figure_3_plot', 'className'),
               Output('img_figure_4_plot', 'className')],
              [Input('textarea_title', 'value'),
               Input('textarea_title', 'title'),
               Input('textarea_description', 'value'),
               Input('html_single_map', 'srcDoc'),
               Input('img_figure_1', 'src'),
               Input('img_figure_2', 'src'),
               Input('img_figure_3', 'src'),
               Input('img_figure_4', 'src')],
              [State('img_figure_1', 'className'),
               State('img_figure_2', 'className'),
               State('img_figure_3', 'className'),
               State('img_figure_4', 'className')])
def update_meta_info_plot(*args):
    return div_plot_empty, *args


# backend for data display, all small single maps display, title display, description display
@app.callback([Output('textarea_title', 'value'),
               Output('textarea_title', 'title'),
               Output('textarea_description', 'value'),
               Output('html_single_map', 'srcDoc')],
              Input('data_changed_dialog_datasets', 'submit_n_clicks'),
              [State('yaml_list_data', 'value'),
               State('main_dropdown', 'value')])
def update_meta_info(_data_changed_approved, selected_file, current_region):
    global saved_data_state

    if check_fired_by != 'yaml_list_data':
        raise PreventUpdate

    # update title
    name = regimes[current_region][selected_file]['regime'].name
    if name == regimes[current_region][selected_file]['regime'].NAME_DEFAULT:
        # if the name of the Regime object is 'Default' use filename
        name = selected_file

    # update description
    description = regimes[current_region][selected_file]['regime'].description

    # update map
    detail_map = Map(zoom_min=0, show_meta=False, map_name=current_region,
                     map_offline=offline)

    # single file location display for small map
    if selected_file:
        detail_map.location_list = [regimes[current_region][selected_file]['regime']]
    try:
        detail_map.load_map(data_file_path=os.path.join(map_path, 'custom_tiles'))
    except NotImplementedError:
        detail_map.map_offline = True
        detail_map.load_map(data_file_path=os.path.join(map_path, 'custom_tiles'))
    detail_map.show_map(filename_html='map_small.html')

    # description_out = (html.H2(children=name), description)
    map_out = open('map_small.html', 'rt').read()

    # save state before proceeding
    saved_data_state['file'] = copy.deepcopy(selected_file)
    saved_data_state['name'] = copy.deepcopy(name)
    saved_data_state['description'] = copy.deepcopy(description)
    saved_data_state['new_file'] = False

    return name, selected_file, description, map_out


@app.callback([Output('modal_export', 'is_open'),
               Output('btn_serve_yaml', 'n_clicks'),
               Output('btn_serve_icex', 'n_clicks'),
               Output('btn_serve_nexd', 'n_clicks')],
              [Input('btn_export', 'n_clicks'),
               Input('btn_close_export', 'n_clicks')],
              [State('modal_export', 'is_open'),
               State('btn_serve_yaml', 'n_clicks'),
               State('btn_serve_icex', 'n_clicks'),
               State('btn_serve_nexd', 'n_clicks')])
def toggle_export_modal(n1, n2, is_open, yaml_n_clicks, icex_n_clicks, nexd_n_clicks):
    def update_n_clicks(n_clicks):
        if source == 'btn_close_export':
            n_clicks = n_clicks + 1 if n_clicks is not None else 1
        else:
            n_clicks = dash.no_update
        return n_clicks

    source = None
    # determine which Input has fired
    ctx = dash.callback_context
    if ctx.triggered:
        source = ctx.triggered[0]['prop_id'].split('.')[0]

    if n1 or n2:
        is_open = not is_open

    yaml_n_clicks = update_n_clicks(yaml_n_clicks)
    icex_n_clicks = update_n_clicks(icex_n_clicks)
    nexd_n_clicks = update_n_clicks(nexd_n_clicks)

    return is_open, yaml_n_clicks, icex_n_clicks, nexd_n_clicks


@app.callback([Output('btn_frm_download_yaml', 'disabled'),
               Output('btn_serve_yaml', 'disabled'),
               Output('frm_download_yaml', 'action')],
              Input('btn_serve_yaml', 'n_clicks'),
              [State('modal_export', 'is_open'),
               State('btn_frm_download_yaml', 'disabled'),
               State('yaml_list_data', 'value'),
               State('textarea_title', 'value'),
               State('textarea_description', 'value'),
               State('data_table', 'data')],
              prevent_initial_call=True)
def download_plain_yaml(_btn_serve_yaml_n_clicks, modal_is_open, download_disabled, filename, title, description, data):
    if modal_is_open:
        uri = os.path.join(client_path, filename)
        ya = get_regime_from_current_dataset(data, title, description, current_figures)
        ya.save_regime(uri)
        return False, True, uri
    else:
        if not download_disabled:
            try:
                os.remove(os.path.join(client_path, filename))
            except OSError:
                pass
        return True, False, dash.no_update


@app.callback([Output('btn_frm_download_icex', 'disabled'),
               Output('btn_serve_icex', 'disabled'),
               Output('frm_download_icex', 'action'),
               Output('p_error_icex', 'children')],
              Input('btn_serve_icex', 'n_clicks'),
              [State('modal_export', 'is_open'),
               State('btn_frm_download_icex', 'disabled'),
               State('yaml_list_data', 'value'),
               State('textarea_title', 'value'),
               State('textarea_description', 'value'),
               State('data_table', 'data')])
def download_icex(_btn_serve_icex_n_clicks, modal_is_open, download_disabled, filename_orig, title, description, data):
    filename = f'icex_{filename_orig}'
    if modal_is_open:
        uri = os.path.join(client_path, filename)
        ya = get_regime_from_current_dataset(data, title, description, current_figures)
        try:
            export.straight_melting(ya, uri)
        except ValueError as error:
            return True, True, dash.no_update, str(error)
        return False, True, uri, ''
    else:
        if not download_disabled:
            try:
                os.remove(os.path.join(client_path, filename))
            except OSError:
                pass
        return True, False, dash.no_update, ''


@app.callback([Output('btn_frm_download_nexd', 'disabled'),
               Output('btn_serve_nexd', 'disabled'),
               Output('radio_nexd', 'options'),
               Output('frm_download_nexd', 'action'),
               Output('p_error_nexd', 'children')],
              Input('btn_serve_nexd', 'n_clicks'),
              [State('modal_export', 'is_open'),
               State('btn_frm_download_nexd', 'disabled'),
               State('yaml_list_data', 'value'),
               State('textarea_title', 'value'),
               State('textarea_description', 'value'),
               State('data_table', 'data'),
               State('radio_nexd', 'value'),
               State('radio_nexd', 'options')])
def download_nexd(_, modal_is_open, download_disabled, filename_orig, title, description, data,
                  mat_type, mat_options):
    filename = f'matprop_{".".join(filename_orig.split(".")[:-1])}'
    if modal_is_open:
        uri = os.path.join(client_path, filename)
        ya = get_regime_from_current_dataset(data, title, description, current_figures)
        try:
            from porodisp.interfaces import write_nexd_matprop
            material = export.nexd.matprop(ya, poroelastic=mat_type != 'elastic', saturated=mat_type != 'poro2f')
            write_nexd_matprop(material, uri, poroelastic=mat_type != 'elastic')
        except ModuleNotFoundError as error:
            for option in mat_options:
                option['disabled'] = True
            return True, True, mat_options, dash.no_update, f'{error}. Please install Python module.'
        except AttributeError or ValueError as error:
            for option in mat_options:
                if option['value'] == mat_type or (option['value'] == 'poro2f' and mat_type == 'poro1f'):
                    option['disabled'] = True
            return True, False, mat_options, dash.no_update, str(error)
        return False, False, dash.no_update, uri, ''
    else:
        if not download_disabled:
            try:
                os.remove(os.path.join(client_path, filename))
            except OSError:
                pass
        for option in mat_options:
            option['disabled'] = False
        return True, False, mat_options, dash.no_update, ''


@app.callback([Output('img_figure_1', 'title'),
               Output('img_figure_2', 'title'),
               Output('img_figure_3', 'title'),
               Output('img_figure_4', 'title'),
               Output('img_figure_1', 'src'),
               Output('img_figure_2', 'src'),
               Output('img_figure_3', 'src'),
               Output('img_figure_4', 'src'),
               Output('img_figure_1', 'className'),
               Output('img_figure_2', 'className'),
               Output('img_figure_3', 'className'),
               Output('img_figure_4', 'className'),
               Output('div_upload_figure', 'className'),
               Output('btn_close_figure', 'n_clicks')],
              [Input('upload_figure', 'contents'),
               Input('btn_delete_img', 'n_clicks'),
               Input('data_changed_dialog_datasets', 'submit_n_clicks')],
              [State('upload_figure', 'filename'),
               State('main_dropdown', 'value'),
               State('yaml_list_data', 'value'),
               State('modal_figures_header', 'children'),
               State('btn_close_figure', 'n_clicks')])
def change_figures(upload_figure_contents, _n_clicks_delete, _data_changed_approved, upload_figure_filename, region,
                   filename, visible_figure_filename, n_clicks_close):
    global current_figures, saved_data_state

    source = None

    # determine which Input has fired
    ctx = dash.callback_context
    if ctx.triggered:
        source = ctx.triggered[0]['prop_id'].split('.')[0]

    if source == 'data_changed_dialog_datasets':
        current_figures = dict(regimes[region][filename]['regime'].figures)
        saved_data_state['figures'] = copy.deepcopy(current_figures)
        n_clicks_close = dash.no_update
    elif source == 'upload_figure':
        current_figures[upload_figure_filename] = {'src': upload_figure_contents,
                                                   'description': Regime.DESCRIPTION_DEFAULT}
        n_clicks_close = dash.no_update
    elif source == 'btn_delete_img':
        n_clicks_close = n_clicks_close + 1 if n_clicks_close is not None else 1
        del current_figures[visible_figure_filename]

    img_title = ['' for _ in range(4)]
    img_src = ['' for _ in range(4)]
    img_class = ['img_figure_hidden' for _ in range(4)]

    i = 0
    for i, figure in enumerate(current_figures.keys()):
        img_title[i] = figure
        img_src[i] = current_figures[figure]['src']
        img_class[i] = 'img_figure'
        if i == 3:
            # do not load more than four figures
            break
    n_figures = i + 1

    # set state of upload "button"
    if n_figures == 2:
        div_class = 'div_upload_figure_block'
    elif n_figures == 4:
        div_class = 'div_upload_figure_hidden'
    else:
        div_class = 'div_upload_figure_inline'

    return *img_title, *img_src, *img_class, div_class, n_clicks_close


@app.callback([Output('modal_figures', 'is_open'),
               Output('modal_figures_header', 'children'),
               Output('modal_figures_body_img', 'src'),
               Output('modal_figures_body_text', 'value'),
               Output('frm_download', 'action')],
              [Input('img_figure_1', 'n_clicks'),
               Input('img_figure_2', 'n_clicks'),
               Input('img_figure_3', 'n_clicks'),
               Input('img_figure_4', 'n_clicks'),
               Input('btn_close_figure', 'n_clicks')],
              [State('img_figure_1', 'title'),
               State('img_figure_2', 'title'),
               State('img_figure_3', 'title'),
               State('img_figure_4', 'title'),
               State('modal_figures_header', 'children'),
               State('modal_figures_body_text', 'value')],
              prevent_initial_call=True)
def toggle_modal_data(_n1, _n2, _n3, _n4, _n_close, title1, title2, title3, title4, filename, description):
    global current_figures

    title_figure = {'img_figure_1': title1, 'img_figure_2': title2, 'img_figure_3': title3, 'img_figure_4': title4}

    # determine which Input has fired
    source = None
    ctx = dash.callback_context
    if ctx.triggered:
        source = ctx.triggered[0]['prop_id'].split('.')[0]

    if source in ['img_figure_1', 'img_figure_2', 'img_figure_3', 'img_figure_4']:
        is_open = True
        filename = title_figure[source]
        src = current_figures[filename]['src']
        description = current_figures[filename]['description']
        # write temporary file
        data = src.encode("utf8").split(b";base64,")[1]
        uri = os.path.join(client_path, filename)
        with open(uri, "wb") as fp:
            fp.write(base64.decodebytes(data))
    else:  # close modal
        if filename != 'Figure':
            # remove temporary file
            try:
                current_figures[filename]['description'] = description
                os.remove(os.path.join(client_path, filename))
            except KeyError or OSError:
                # KeyError occurs if file was deleted in GUI in the meantime.
                pass
        is_open = False
        filename = dash.no_update
        src = dash.no_update
        description = dash.no_update
        uri = dash.no_update

    return is_open, filename, src, description, uri


@app.callback([Output('modal_figures_plot', 'is_open'),
               Output('modal_figures_header_plot', 'children'),
               Output('modal_figures_body_img_plot', 'src'),
               Output('modal_figures_body_text_plot', 'value'),
               Output('frm_download_plot', 'action')],
              [Input('img_figure_1_plot', 'n_clicks'),
               Input('img_figure_2_plot', 'n_clicks'),
               Input('img_figure_3_plot', 'n_clicks'),
               Input('img_figure_4_plot', 'n_clicks'),
               Input('btn_close_figure_plot', 'n_clicks')],
              [State('modal_figures_plot', 'is_open'),
               State('img_figure_1', 'title'),
               State('img_figure_2', 'title'),
               State('img_figure_3', 'title'),
               State('img_figure_4', 'title'),
               State('modal_figures_header_plot', 'children')],
              prevent_initial_call=True)
def toggle_modal_plot(_n1, _n2, _n3, _n4, _n_close, _is_open, title1, title2, title3, title4, title):
    title_figure = {'img_figure_1': title1, 'img_figure_2': title2, 'img_figure_3': title3, 'img_figure_4': title4}

    # determine which Input has fired
    source = None
    ctx = dash.callback_context
    if ctx.triggered:
        source = ctx.triggered[0]['prop_id'].split('.')[0]

    if source in ['img_figure_1_plot', 'img_figure_2_plot', 'img_figure_3_plot', 'img_figure_4_plot']:
        is_open = True
        title = title_figure[source]
        src = current_figures[title]['src']
        description = current_figures[title]['description']
        data = src.encode("utf8").split(b";base64,")[1]
        uri = os.path.join(client_path, title)
        with open(uri, "wb") as fp:
            fp.write(base64.decodebytes(data))
    else:
        if title != 'Figure':
            # remove temporary file
            try:
                os.remove(os.path.join(client_path, title))
            except OSError:
                pass
        is_open = False
        title = dash.no_update
        src = dash.no_update
        description = dash.no_update
        uri = dash.no_update

    return is_open, title, src, description, uri


# backend of large map display in the Overview tab
@app.callback(Output('html_map', 'srcDoc'),
              [Input('yaml_list_map', 'value')],
              [State('main_dropdown', 'value')])
def update_map(selected_files, current_region):
    if current_region == '_default':
        return 'No map for _default.'
    main_map = Map(zoom_start=2, map_name=current_region, map_offline=offline)
    if selected_files:
        main_map.location_list = [regimes[current_region][selected_file]['regime'] for selected_file in selected_files]
    try:
        main_map.load_map(data_file_path=os.path.join(map_path, 'custom_tiles'))
    except NotImplementedError:
        main_map.map_offline = True
        main_map.load_map(data_file_path=os.path.join(map_path, 'custom_tiles'))
    main_map.show_map(filename_html='map.html')
    return open('map.html', 'rt').read()


# callback for the data display input
@app.callback([Output('data_table', 'data'),
               Output('data_table', 'columns'),
               Output('data_table', 'tooltip_data'),
               Output('data_table', 'style_data_conditional'),
               Output('graph_dropdown', 'options'),
               Output('graph_dropdown', 'value')],
              [Input('data_changed_dialog_datasets', 'submit_n_clicks'),
               Input('btn_add_column', 'n_clicks'),
               Input('btn_add_row', 'n_clicks')],
              [State('yaml_list_data', 'value'),
               State('main_dropdown', 'value'),
               State('data_table', 'data'),
               State('data_table', 'columns'),
               State('input_add_column', 'value')])
# function for the display of the data
def update_data(_data_changed_approved, add_column_click, add_row_click, selected_file, current_region, prev_data,
                prev_columns, add_column_name):
    if check_fired_by != 'yaml_list_data':
        raise PreventUpdate

    source = None
    # determine which Input has fired
    ctx = dash.callback_context
    if ctx.triggered:
        source = ctx.triggered[0]['prop_id'].split('.')[0]

    if source == 'btn_add_column' and add_column_click:
        # first check if column is already present
        prev_column_names = [column['name'] for column in prev_columns]
        if add_column_name not in prev_column_names:
            # add columns to existing data
            prev_columns.append({'id': add_column_name, 'name': add_column_name, 'selectable': True, 'renamable': True,
                                 'deletable': True})
            if add_column_name in dropdown_in_table:
                prev_columns[-1].update({'presentation': 'dropdown'})
        return dash.no_update, prev_columns, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    elif source == 'btn_add_row' and add_row_click:
        # add rows to existing data
        if add_row_click > 0:
            prev_data.append({c['id']: '' for c in prev_columns})
        return prev_data, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    else:
        # e.g. source == 'yaml_list_data' or initial call
        # fill table from scratch
        data = regimes[current_region][selected_file]['props'].transpose().to_dict('records')
        for j, name in enumerate(regimes[current_region][selected_file]['props'].columns):
            data[j]['property'] = name

        columns = [{'name': 'property', 'id': 'property'}]

        for prop in predefined_column_order:
            if prop in regimes[current_region][selected_file]['props'].transpose().columns:
                columns.extend([{'name': prop, 'id': prop, 'selectable': True, 'renamable': True, 'deletable': True}])

        for prop in regimes[current_region][selected_file]['props'].transpose().columns:
            if prop not in regimes[current_region][selected_file][
                'regime'].HIDDEN_PARAMS and prop not in predefined_column_order:
                columns.extend([{'name': prop, 'id': prop, 'selectable': True, 'renamable': True, 'deletable': True}])

        for column in columns:
            if column['name'] in dropdown_in_table:
                column.update({'presentation': 'dropdown'})

        # tooltip for datatable in the data tab
        tooltip_data = [
            {column: {'value': str(value) if len(str(value)) >= 35 - 2 * len(row.items()) else ''}
             for column, value in row.items()} for row in data
        ]
        plot_options = [{'label': item['property'], 'value': item['property'],
                         'disabled': True if 'type' not in item or item['type'] not in ['expression',
                                                                                        'tabulated'] else False} for
                        item in data]

        # save state before proceeding
        saved_data_state['table_data'] = copy.deepcopy(data)

        # hide nan values
        style_data_conditional = basic_style_data_conditional
        style_data_conditional.extend([
            {'if': {'filter_query': '{{{}}} = "nan"'.format(col['name']), 'column_id': col['name'],
                    'row_index': 'odd'}, 'color': 'white'}
            for col in columns])
        style_data_conditional.extend([
            {'if': {'filter_query': '{{{}}} = "nan"'.format(col['name']), 'column_id': col['name'],
                    'row_index': 'even'}, 'color': 'var(--EvenRow)'}
            for col in columns])

        return data, columns, tooltip_data, style_data_conditional, plot_options, None


# function for select constants or variables
@app.callback(
    [Output('graph-multivariables', 'options'),
     Output('graph-singlevariable', 'options')],
    [Input('graph_dropdown', 'value')],
    [State('yaml_list_data', 'value'),
     State('main_dropdown', 'value')])
def set_single_multi_options(variable, selected_file, current_region):
    if variable is None:
        raise PreventUpdate
    else:
        current_variable = regimes[current_region][selected_file]['regime'].props[variable]

        try:
            list_variable = list(current_variable['variable'].keys())
        except AttributeError:  # if it is scalar single variable
            list_variable = ['x']
        return [{'label': i, 'value': i} for i in list_variable], [{'label': i, 'value': i} for i in list_variable]


# function for storing temporary data in a dictionary
@app.callback(
    Output('btn_memory', 'data'),
    Output('store_rejected_dialog', 'displayed'),
    Output('store_rejected_dialog', 'message'),
    [Input('btn_store', 'n_clicks')],
    [State('graph_dropdown', 'value'),
     State('graph-multivariables', 'value'),
     State('graph-singlevariable', 'value'),
     State('graph_constant_x', 'value'),
     State('graph_min_x', 'value'),
     State('graph_max_x', 'value'),
     State('btn_memory', 'data'),
     State('yaml_list_data', 'value'),
     State('main_dropdown', 'value')
     ]
)
def store_data(n_clicks_store, variable, selected_multivariables, singlevariable, constant_value, minimum, maximum,
               data, selected_file, current_region):
    message = ''
    if n_clicks_store is None:
        # prevent the None callbacks is important with the store component.
        # you don't want to update the store for nothing.
        raise PreventUpdate

    if variable and n_clicks_store > 0:

        data = data or {variable: {}}

        if not data.__contains__(variable):  # if we change to a new property, we then clean and reset the data
            data = {variable: {}}

        if singlevariable in selected_multivariables:  # the selected variable is in the multivariables list,
            # it means we want to include the min and max
            if minimum is None or maximum is None or minimum == '' or maximum == '':
                message = u'ERROR: Specify minimum and maximum for {}!'.format(singlevariable)
            else:
                data[variable].update({singlevariable: [float(minimum), float(maximum)]})
        else:  # this means the selected variable is a constant
            if constant_value is None or constant_value == '':
                message = u'ERROR: Specify a constant value for {}!'.format(singlevariable)
            else:
                data[variable].update({singlevariable: float(constant_value)})

        data[variable].update({'selected_multivariables': selected_multivariables})

        if message == '':  # if message is None
            return data, False, message
        else:
            return data, True, message

    else:  # if variable = None or n_clicks_store = 0
        if variable:

            data_type = regimes[current_region][selected_file]['regime'].props[variable]['type']
            if data_type == 'expression':
                raise PreventUpdate
            else:
                return None, False, message
        else:
            raise PreventUpdate


@app.callback(Output('btn_memory', 'clear_data'),
              Output('graph-multivariables', 'value'),
              Output('graph-singlevariable', 'value'),
              Output('btn_plot', 'n_clicks'),
              Output('btn_store', 'n_clicks'),
              [Input('graph_dropdown', 'value'),
               Input('btn_plot', 'n_clicks'),
               Input('btn_store', 'n_clicks')],
              [State('btn_memory', 'data'),
               State('graph-multivariables', 'value'),
               State('graph-singlevariable', 'value'),
               State('yaml_list_data', 'value'),
               State('main_dropdown', 'value')
               ])
def clear_clickanddata(variable, n_clicks_plot, n_clicks_store, data, multi, single, selected_file,
                       current_region):  # when change type of
    # variables, clear n_clicks and data. Avoid plotting the figure when clicking store
    if variable is None:
        raise PreventUpdate

    if variable:
        data_type = regimes[current_region][selected_file]['regime'].props[variable]['type']
        if data_type == 'expression':  # only for 'expression' type

            try:
                if variable == list(data.keys())[0]:  # if type of variable is the same as before.
                    if not (multi == data[variable]['selected_multivariables']):  # if we change selected_multivariables
                        return True, multi, single, 0, n_clicks_store
                    else:
                        return False, multi, single, n_clicks_plot, n_clicks_store
                else:  # if variable is not the same
                    return True, None, None, 0, 0
            except AttributeError:  # before storing any values, data = None
                if n_clicks_store > 0:
                    return True, multi, single, n_clicks_plot, n_clicks_store
                else:  # if we do not store anything but change the type of variable
                    return True, None, None, 0, n_clicks_store
        else:  # for tabulated properties
            # return True, None, None, n_clicks_plot, 0
            return True, None, None, 1, 0  # directly plot tabulated values without clicking plot button
    else:
        return False, None, None, 0, 0


@app.callback(Output('graph_plot', 'children'),
              [Input('btn_plot', 'n_clicks'),
               Input('btn_memory', 'modified_timestamp')
               ],
              [State('btn_memory', 'data'),
               State('graph_dropdown', 'value'),
               State('graph-multivariables', 'value'),
               State('graph-singlevariable', 'value'),
               State('graph_constant_x', 'value'),
               State('graph_min_x', 'value'),
               State('graph_max_x', 'value'),
               State('yaml_list_data', 'value'),
               State('main_dropdown', 'value')])
def show_plot(n_clicks, ts, data, variable, selected_multivariables, singlevariable, constant_value, minimum, maximum,
              selected_file, current_region,
              use_plotly=True):
    if ts is None:
        raise PreventUpdate

    if variable and n_clicks > 0:

        data_type = regimes[current_region][selected_file]['regime'].props[variable]['type']
        current_variable = regimes[current_region][selected_file]['regime'].props[variable]
        plot_kwargs = {'gui': True, 'use_plotly': use_plotly}

        if data_type == 'expression':

            data = data or {variable: {}}

            if len(selected_multivariables) >= 3:
                return html.P('The number of variables cannot exceed two !')

            # check for empty entries
            if singlevariable in selected_multivariables:
                if minimum is None or maximum is None or minimum == '' or maximum == '':
                    return html.P(u'ERROR: Specify minimum and maximum for {}!'.format(singlevariable))
            else:
                if constant_value is None or constant_value == '':
                    return html.P(u'ERROR: Specify a constant value for {}!'.format(singlevariable))

            # check if we have all the available values ready for plotting
            try:
                list_variable = list(current_variable['variable'].keys())
            except AttributeError:
                list_variable = ['x']

            if not (set(list_variable) <= data[variable].keys()):
                return html.P(
                    u'WARNING: Missing value(s) for {}!'.format(set(list_variable) - set(data[variable].keys())))
            else:  # this means we have all variables have set to the value(s), and ready for plotting
                cst = set(list_variable) - set(selected_multivariables)  # constant variable
                cst_list = dict(filter(lambda i: i[0] in cst, data[variable].items()))  # constant variable lists
                multi_list = dict(
                    filter(lambda i: i[0] in selected_multivariables, data[variable].items()))  # multivariable lists

                plot_kwargs.update({'multivariable': {'cst': cst_list, 'noncst': multi_list}})

        fig = regimes[current_region][selected_file]['regime'].plot_property(variable, **plot_kwargs)
        if not use_plotly:
            fig = mpl_to_plotly(fig)
        return dcc.Graph(style={'height': '100%', 'width': '100%'}, figure=fig)
    else:
        raise PreventUpdate


@app.callback([Output('graph_constant_x', 'disabled'),
               Output('graph_min_x', 'disabled'),
               Output('graph_max_x', 'disabled'),
               Output('btn_store', 'disabled'),
               Output('btn_plot', 'disabled'),
               Output('plot_rejected_dialog', 'displayed'),
               Output('plot_rejected_dialog', 'message'),
               Output('graph-multivariables', 'disabled'),
               Output('graph-singlevariable', 'disabled')
               ],
              [Input('graph_dropdown', 'value'),
               Input('graph-multivariables', 'value'),
               Input('graph-singlevariable', 'value'),
               Input('btn_store', 'n_clicks')
               ],
              [State('yaml_list_data', 'value'),
               State('main_dropdown', 'value')])
def enable_plot(variable, selected_multivariables, selected_singlevariable, n_clicks_store, selected_file,
                current_region):
    message = ''
    if variable is not None and selected_file is not None and current_region is not None:
        current_variable = regimes[current_region][selected_file]['regime'].props[variable]
        state = {'coordinate': (True, True, True, True, True, False, message, True, True),
                 'scalar': (True, True, True, True, True, False, message, True, True),
                 'array': (True, True, True, True, True, False, message, True, True),
                 'expression': (False, False, False, False, False, False, message, False, False),
                 'tabulated': (True, True, True, True, True, False, message, True, True),
                 'string': (False, True, True, False, True, False, message, True, True)}
        if current_variable['type'] == 'expression':
            if selected_multivariables:
                if len(selected_multivariables) >= 3:
                    message = 'The number of variables cannot exceed two !'
                    return True, True, True, True, True, True, message, False, False

            if selected_multivariables and selected_singlevariable:
                if selected_singlevariable in selected_multivariables:  # store min and max
                    if n_clicks_store > 0:
                        return True, False, False, False, False, False, message, False, False
                    else:  # if data is None, disable plot
                        return True, False, False, False, True, False, message, False, False
                else:  # store constant
                    if n_clicks_store > 0:
                        return False, True, True, False, False, False, message, False, False
                    else:  # if data is None, disable plot
                        return False, True, True, False, True, False, message, False, False
            else:
                return True, True, True, True, True, False, message, False, False

        else:
            return state[current_variable['type']]
    else:
        return True, True, True, True, True, False, message, True, True


# backend for the save file button
@app.callback([Output('save_dialog', 'displayed'),
               Output('save_dialog', 'message')],
              Input('btn_save_file', 'n_clicks'),
              State('yaml_list_data', 'value'))
def save_yaml_file(n_clicks_save, current_file_name):
    # Check if file already exists or not and raise confirm dialog.
    if n_clicks_save:
        return True, f'Do you want to replace the existing file "{current_file_name}"?'
    else:
        raise PreventUpdate


# backend for the save file as button
@app.callback([Output('save_as_dialog', 'displayed'),
               Output('save_as_dialog', 'message'),
               Output('input_save_file_as', 'value')],
              [Input('btn_save_file_as', 'n_clicks')],
              [State('main_dropdown', 'value'),
               State('input_save_file_as', 'value')])
def save_yaml_file_as(n_clicks_save_as, current_region_name, file_name):
    # Add correct file extension if file_name not ends with '.yaml'
    if file_name.split('.')[-1] != 'yaml':
        file_name += '.yaml'

    # Check if file already exists or not and raise confirm dialog.
    if n_clicks_save_as:
        if file_name in regimes[current_region_name].keys():
            message = f'File "{file_name}" already exists. Do you want to replace it with the current data?'
            return True, message, file_name
        else:
            message = f'Create new file "{file_name}" in current folder and save data?'
            return True, message, file_name
    else:
        raise PreventUpdate


# backend for the save file button
@app.callback([Output('delete_dialog', 'displayed'),
               Output('delete_dialog', 'message')],
              Input('btn_delete_file', 'n_clicks'),
              State('yaml_list_data', 'value'))
def delete_yaml_file(n_clicks_delete, current_file_name):
    # Check if file already exists or not and raise confirm dialog.
    if n_clicks_delete:
        return True, f'Do you want to delete the file "{current_file_name}"?'
    else:
        raise PreventUpdate


# backend for the add new file button
@app.callback([Output('newfile_dialog', 'displayed'),
               Output('newfile_dialog', 'message'),
               Output('input_add_file', 'value')],
              Input('data_changed_dialog_datasets', 'submit_n_clicks'),
              [State('main_dropdown', 'value'),
               State('input_add_file', 'value')])
def new_yaml_file(_data_changed_approved, current_region_name, file_name):
    if check_fired_by != 'btn_add_file':
        raise PreventUpdate

    # Add correct file extension if file_name not ends with '.yaml'
    if file_name.split('.')[-1] != 'yaml':
        file_name += '.yaml'

    # Check if file already exists or not and raise confirm dialog.
    if file_name in regimes[current_region_name].keys():
        return True, f'File "{file_name}" already exists. Do you want to replace it with an empty file?', file_name
    else:
        return True, f'Create new file "{file_name}" in current folder?', file_name


@app.callback([Output('upload_dialog', 'displayed'),
               Output('upload_dialog', 'message'),
               Output('upload_rejected_dialog', 'displayed'),
               Output('upload_rejected_dialog', 'message')],
              Input('data_changed_dialog_datasets', 'submit_n_clicks'),
              [State('upload_file', 'contents'),
               State('upload_file', 'filename'),
               State('main_dropdown', 'value')],
              prevent_initial_call=True)
def upload_file(_data_changed_approved, file_content, file_name: str, current_region_name):
    if check_fired_by != 'upload_file':
        raise PreventUpdate

    message = ''
    # check if uploaded file is a yaml file
    if file_name.endswith('.yaml'):
        from yaml.parser import ParserError
        try:
            file_bytes = base64.b64decode(file_content.split(',')[-1])
            _ = yaml.load(file_bytes.decode('unicode_escape'), Loader=PrettySafeLoader)
            is_yaml_file = True
            message += f'Upload {file_name} to Map name {current_region_name}'
            # check if file already exists
            if file_name in regimes[current_region_name].keys():
                message += ' and replace existing file?'
            else:
                message += '?'
        except ParserError:
            is_yaml_file = False
    else:
        is_yaml_file = False

    if is_yaml_file:
        return True, message, False, dash.no_update
    else:
        message += f'Cannot upload. File {file_name} is not a yaml-file.'
        return False, dash.no_update, True, message


# backend for writing files
@app.callback([Output('input_filter', 'n_submit'),
               Output('upload_file', 'contents')],
              [Input('newfile_dialog', 'submit_n_clicks'),
               Input('save_dialog', 'submit_n_clicks'),
               Input('save_as_dialog', 'submit_n_clicks'),
               Input('upload_dialog', 'submit_n_clicks'),
               Input('delete_dialog', 'submit_n_clicks')],
              [State('main_dropdown', 'value'),
               State('yaml_list_data', 'value'),
               State('textarea_title', 'value'),
               State('textarea_description', 'value'),
               State('data_table', 'data'),
               State('btn_filter', 'n_clicks'),
               State('input_add_file', 'value'),
               State('input_save_file_as', 'value'),
               State('upload_file', 'contents'),
               State('upload_file', 'filename')],
              prevent_initial_call=True)
def write_yaml_file(newfile_dialog_n_clicks, save_dialog_n_clicks, save_as_dialog_n_clicks, upload_dialog_n_clicks,
                    delete_dialog_n_clicks, current_region_name, current_file_name, title, des, data, n_clicks_filter,
                    new_file_name, save_as_file_name, upload_file_content, upload_file_name):
    global deep_update_necessary, saved_data_state

    source = None
    # determine which Input has fired
    ctx = dash.callback_context
    if ctx.triggered:
        source = ctx.triggered[0]['prop_id'].split('.')[0]

    ya = Regime()
    formated_data = {}
    # assigning path of the new/updated file save folder
    if source == 'newfile_dialog' and newfile_dialog_n_clicks:
        # returning empty dictionary
        write_file_name = new_file_name
    elif source == 'save_dialog' and save_dialog_n_clicks:
        write_file_name = current_file_name
    elif source == 'save_as_dialog' and save_as_dialog_n_clicks:
        write_file_name = save_as_file_name
    elif source == 'upload_dialog' and upload_dialog_n_clicks:
        write_file_name = upload_file_name
    elif source == 'delete_dialog' and delete_dialog_n_clicks:
        write_file_name = current_file_name
    else:
        return dash.no_update, dash.no_update

    filepath = os.path.join(os.path.realpath(os.path.dirname(__file__)), os.pardir, yaml_path, current_region_name,
                            write_file_name)

    if source in ['delete_dialog']:
        os.remove(filepath)
        saved_data_state['file'] = None
        saved_data_state['new_file'] = False
    elif source in ['upload_dialog']:
        with open(filepath, 'w', newline='') as file:
            file_bytes = base64.b64decode(upload_file_content.split(',')[-1])
            file.write(file_bytes.decode('unicode_escape'))
        saved_data_state['file'] = copy.deepcopy(write_file_name)
        saved_data_state['new_file'] = True
        upload_file_content = ''
    else:
        if source in ['save_dialog', 'save_as_dialog']:
            ya = get_regime_from_current_dataset(data, title, des, current_figures)
        else:
            ya.props = formated_data
        ya.save_regime(filepath)

        # save state before proceeding
        saved_data_state['file'] = copy.deepcopy(write_file_name)
        saved_data_state['name'] = copy.deepcopy(title)
        saved_data_state['description'] = copy.deepcopy(des)
        saved_data_state['figures'] = copy.deepcopy(current_figures)
        saved_data_state['table_data'] = copy.deepcopy(data)
        saved_data_state['new_file'] = True
        if source == 'save_dialog':
            deep_update_necessary = True
    if source in ['upload_dialog']:
        return n_clicks_filter + 1, upload_file_content
    else:
        return n_clicks_filter + 1, dash.no_update


@app.callback(Output('btn_filter', 'n_clicks'),
              [Input('input_filter', 'n_submit')],
              [State('btn_filter', 'n_clicks')])
def filter_relay(n_submit_filter, n_clicks_filter):
    # If Enter key was pressed in filter mask, add an immaginary click to the corresponding button
    if n_submit_filter:
        return n_clicks_filter + 1
    else:
        raise PreventUpdate


@app.callback(Output('btn_add_file', 'n_clicks'),
              [Input('input_add_file', 'n_submit')],
              [State('btn_add_file', 'n_clicks')])
def add_file_relay(n_submit_add_file, n_clicks_add_file):
    # If Enter key was pressed in add new file mask, add an immaginary click to the corresponding button
    if n_submit_add_file:
        return n_clicks_add_file + 1
    else:
        raise PreventUpdate


@app.callback(Output('btn_add_column', 'n_clicks'),
              [Input('input_add_column', 'n_submit')],
              [State('btn_add_column', 'n_clicks')])
def add_column_relay(n_submit_add_column, n_clicks_add_column):
    # If Enter key was pressed in add new file mask, add an immaginary click to the corresponding button
    if n_submit_add_column:
        return n_clicks_add_column + 1
    else:
        raise PreventUpdate


@app.callback(Output('btn_save_file_as', 'n_clicks'),
              [Input('input_save_file_as', 'n_submit')],
              [State('btn_save_file_as', 'n_clicks')])
def save_file_as_relay(n_submit_save_file_as, n_clicks_save_file_as):
    # If Enter key was pressed in add new file mask, add an immaginary click to the corresponding button
    if n_submit_save_file_as:
        return n_clicks_save_file_as + 1
    else:
        raise PreventUpdate


if __name__ == '__main__':
    load_lib_path()
    # General settings:
    settings = {
        "gui_title": 'Data Hub',
        # for the image of logo
        "logo_data_hub_png": 'logo_data_hub.png',
        "logo_data_hub_png_title": 'Data Hub Logo',
        "logo_png": 'logo.png',
        "uni_logo_png": 'uni_logo.png',
        "main_dropdown_title": 'Map name:'
    }

    setup_html_gui(**settings)

    app.run_server(debug=False)
