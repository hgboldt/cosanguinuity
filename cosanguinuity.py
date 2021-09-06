# Cosanguinuity - Determine relationships between ancestors and spouses
#
# Copyright (C) 2021  Hans Boldt
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

"""
Module cosanguinuity.py

Gramplet for reporting on pedigree collapse and spousal cosanguinuity for
the active person.

Exports:

class CosanguinuityGramplet

"""

#-------------------#
# Python modules    #
#-------------------#
import threading
import pdb

#-------------------#
# Gramps modules    #
#-------------------#
from gramps.gen.plug import Gramplet
from gramps.gen.lib import Person
from gramps.gen.plug.menu import EnumeratedListOption
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gui.utils import color_graph_box

#------------------#
# Gtk modules      #
#------------------#
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk

#-----------------------------------#
# Other related gramplet modules    #
#-----------------------------------#
from pedigree import Pedigree, SimpleCache
from cosformatter import CosFormatter, SimpleStringBuffer

#------------------#
# Translation      #
#------------------#
try:
    _trans = glocale.get_addon_translator(__file__)
    _ = _trans.gettext
except ValueError:
    _ = glocale.translation.sgettext
ngettext = glocale.translation.ngettext # else "nearby" comments are ignored

#-------------#
# Messages    #
#-------------#
MSG_NO_FAMILY_TREE = _('No Family Tree loaded.')
MSG_MOVE_MOUSE_FOR_OPTS = _('Move mouse over links for options')
MSG_CLICK_TO_ACTIVATE = _('Click to make active\nRight-click to edit')
MSG_VIEW_STYLE = _('View style')
MSG_SINGLE_PANE = _('Single pane')
MSG_NOTEBOOK = _('Notebook')
MSG_COPY_TO_CLIPBOARD = _('Copy')
MSG_CLOSE = _('Close')
MSG_SHOW_PEDIGREES = _('Display pedigrees')
MSG_PED_COLLAPSE = _('Pedigree collapse')
MSG_SPOUSAL_COSANGUINUITY = _('Spousal cosanguinity')
MSG_DESCENDANTS = _('Descendants')

#---------------------#
# Module constants    #
#---------------------#
VIEW_STYLE_SINGLE = 'single'
VIEW_STYLE_TABBED = 'tabbed'
PEDIGREE_CACHE_SIZE = 30
DATA_CACHE_SIZE = 30


def get_spouses(db, person_handle):
    """
    Return list of spouses for given person.
    """
    spouses = list()
    person = db.get_person_from_handle(person_handle)
    gender = person.get_gender()

    # Loop through all families
    for family_handle in person.get_family_handle_list():
        family = db.get_family_from_handle(family_handle)
        if not family:
            continue

        if gender == Person.MALE:
            spouse_handle = family.get_mother_handle()
        else:
            spouse_handle = family.get_father_handle()

        if spouse_handle:
            spouses.append(spouse_handle)

    return spouses


#--------------------------------#
#                                #
# CosanguinuityGramplet class    #
#                                #
#--------------------------------#
class CosanguinuityGramplet(Gramplet):
    """
    Cosanguinuity gramplet.
    """

    # class variables
    cache = SimpleCache(DATA_CACHE_SIZE)


    def __init__(self, *args, **kwargs):
        """
        __init__
        """
        self.active_handle = None
        self.view_style = VIEW_STYLE_SINGLE
        self.content_box = None
        self.title_section = None
        self.ped_collapse_section = None
        self.cosanguinuity_section = None
        self.single_pane_button = None
        self.tabbed_button = None
        self.tab_displayed = None
        self.pedigrees = None

        super().__init__(*args, **kwargs)


    def init(self):
        """
        Gramplet initialization. Overrides method in class Gramplet.
        """
        self.set_text(MSG_NO_FAMILY_TREE)
        self.set_tooltip(MSG_MOVE_MOUSE_FOR_OPTS)
        self.set_use_markup(True)
        self.link_tooltip = MSG_CLICK_TO_ACTIVATE


    def post_init(self):
        """
        Gramplet post-initialization.

        Overrides method in class Gramplet.
        """
        self.gui.WIDGET = self.build_gui()
        self.gui.get_container_widget().remove(self.gui.textview)
        self.gui.get_container_widget().add(self.gui.WIDGET)


    def build_options(self):
        """
        Build options.

        Overrides method in class Gramplet.
        """
        view_option = EnumeratedListOption(MSG_VIEW_STYLE, self.view_style)
        view_option.add_item(VIEW_STYLE_SINGLE, MSG_SINGLE_PANE)
        view_option.add_item(VIEW_STYLE_TABBED, MSG_NOTEBOOK)
        self.add_option(view_option)


    def on_load(self):
        """
        Invoked when loading gramplet.

        Overrides method in class Gramplet.
        """
        if len(self.gui.data) == 1:
            self.view_style = self.gui.data[0]


    def save_options(self):
        """
        Get the options prior to being displayed on the "Configure the
        active view" dialog.

        Overrides method in class Gramplet.
        """
        self.view_style = self.get_option(MSG_VIEW_STYLE).get_value()


    def save_update_options(self, obj=None):
        """
        Save update options.

        Overrides method in class Gramplet.
        """
        self.view_style = self.get_option(MSG_VIEW_STYLE).get_value()
        self.single_pane_button.set_active(self.view_style == VIEW_STYLE_SINGLE)
        self.tabbed_button.set_active(self.view_style == VIEW_STYLE_TABBED)
        self.gui.data = [self.view_style]
        self.update()


    def db_changed(self):
        """
        Overrides method in class Gramplet.

        Note: If an person, family, or event changes, any pedigree may change.
        """
        self.connect(self.dbstate.db, 'person-add', self.database_changed)
        self.connect(self.dbstate.db, 'person-delete', self.database_changed)
        self.connect(self.dbstate.db, 'person-update', self.database_changed)
        self.connect(self.dbstate.db, 'person-rebuild', self.database_changed)

        self.connect(self.dbstate.db, 'event-add', self.database_changed)
        self.connect(self.dbstate.db, 'event-delete', self.database_changed)
        self.connect(self.dbstate.db, 'event-update', self.database_changed)
        self.connect(self.dbstate.db, 'event-rebuild', self.database_changed)

        self.connect(self.dbstate.db, 'family-add', self.database_changed)
        self.connect(self.dbstate.db, 'family-delete', self.database_changed)
        self.connect(self.dbstate.db, 'family-update', self.database_changed)
        self.connect(self.dbstate.db, 'family-rebuild', self.database_changed)

        Pedigree.clear_pedigree_cache()
        self.cache.clear()


    def database_changed(self, *arg):
        """
        On any change to any person, family, or event, any cached data may also
        change. Therefore, the caches must be cleared of any saved data.
        """
        Pedigree.clear_pedigree_cache()
        self.cache.clear()
        self.update()


    def active_changed(self, handle):
        """
        Called when the active person is changed.

        Overrides method in class Gramplet.
        """
        self.update()


    def build_gui(self):
        """
        Build the GUI for this gramplet.
        """
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.content_box.homogenous = False
        self.content_box.set_border_width(0)

        self.title_section = Gtk.Label(label='')
        self.title_section.set_halign(Gtk.Align.START)
        self.title_section.set_justify(Gtk.Justification.LEFT)
        self.content_box.pack_start(self.title_section, False, False, 5)

        self.ped_collapse_section = Gtk.Label(label='')
        self.ped_collapse_section.set_valign(Gtk.Align.START)
        self.ped_collapse_section.set_halign(Gtk.Align.START)
        self.ped_collapse_section.set_justify(Gtk.Justification.LEFT)
        self.ped_collapse_section.connect('activate-link',
                                          self.on_activate_link)

        self.cosanguinuity_section = Gtk.Label(label='')
        self.cosanguinuity_section.set_valign(Gtk.Align.START)
        self.cosanguinuity_section.set_halign(Gtk.Align.START)
        self.cosanguinuity_section.set_justify(Gtk.Justification.LEFT)
        self.cosanguinuity_section.connect('activate-link',
                                           self.on_activate_link)

        window = self._make_content_widgets()
        self.content_box.pack_start(window, True, True, 5)

        button_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.single_pane_button = Gtk.RadioButton(label=MSG_SINGLE_PANE)
        self.single_pane_button.set_active(self.view_style == VIEW_STYLE_SINGLE)
        self.single_pane_button.connect('toggled', self.on_button_toggled,
                                        VIEW_STYLE_SINGLE)
        self.tabbed_button = Gtk.RadioButton.new_with_label_from_widget \
                            (self.single_pane_button, MSG_NOTEBOOK)
        self.tabbed_button.set_active(self.view_style == VIEW_STYLE_TABBED)
        self.tabbed_button.connect('toggled', self.on_button_toggled,
                                   VIEW_STYLE_TABBED)

        buttons.pack_start(self.single_pane_button, False, False, 5)
        buttons.pack_start(self.tabbed_button, False, False, 5)
        button_bar.pack_start(buttons, False, False, 5)

        copy_button = Gtk.Button.new_with_label(MSG_COPY_TO_CLIPBOARD)
        copy_button.connect('clicked', self.on_copy_to_clipboard)
        button_bar.pack_start(copy_button, False, False, 5)

        pedigree_button = Gtk.Button.new_with_label(MSG_SHOW_PEDIGREES)
        pedigree_button.connect('clicked', self.on_click_show_pedigrees)
        button_bar.pack_start(pedigree_button, False, False, 5)

        self.content_box.pack_start(button_bar, False, False, 0)

        self.content_box.show_all()
        return self.content_box


    def refresh_content(self):
        """
        Refresh the content of the gramplet.
        """
        children = self.content_box.get_children()
        content = children[1]
        buttons = children[2]
        self.content_box.remove(buttons)
        self.content_box.remove(content)

        parent = self.ped_collapse_section.get_parent()
        parent.remove(self.ped_collapse_section)
        parent = self.cosanguinuity_section.get_parent()
        parent.remove(self.cosanguinuity_section)

        window = self._make_content_widgets()
        self.content_box.pack_start(window, True, True, 5)
        self.content_box.pack_start(buttons, False, False, 5)
        self.content_box.show_all()


    def _make_content_widgets(self):
        """
        Make the content widgets based on current view style
        """
        if self.view_style == VIEW_STYLE_SINGLE:
            window = Gtk.ScrolledWindow()
            single_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            single_box.set_halign(Gtk.Align.START)
            single_box.pack_start(self.ped_collapse_section, False, False, 0)
            single_box.pack_start(self.cosanguinuity_section, False, False, 0)
            window.add(single_box)
            return window

        # Notebook style
        window = Gtk.Notebook()
        pedcoll_scrolled = Gtk.ScrolledWindow()
        pedcoll_scrolled.add(self.ped_collapse_section)
        window.append_page(pedcoll_scrolled,
                           Gtk.Label(label=MSG_PED_COLLAPSE))
        pedcoll_scrolled = Gtk.ScrolledWindow()
        pedcoll_scrolled.add(self.cosanguinuity_section)
        window.append_page(pedcoll_scrolled,
                           Gtk.Label(label=MSG_SPOUSAL_COSANGUINUITY))
        window.connect('switch_page', self.on_switch_page)
        return window


    def get_view_selection(self):
        """
        Return view style based on radio button settings.
        """
        if self.single_pane_button.get_active():
            return VIEW_STYLE_SINGLE
        return VIEW_STYLE_TABBED


    def on_switch_page(self, _notebook, _window, tab_index):
        """
        Page of notebook is selected
        """
        self.tab_displayed = tab_index


    def on_copy_to_clipboard(self, button):
        """
        Copy text of visible panel to clipboard
        """
        text = self.title_section.get_text() + "\n\n"

        if self.view_style == VIEW_STYLE_SINGLE:
            text += self.ped_collapse_section.get_text() + \
                   self.cosanguinuity_section.get_text()
        elif self.tab_displayed == 0:
            text += self.ped_collapse_section.get_text()
        else:
            text += self.cosanguinuity_section.get_text()

        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)

        # Temporarily add '* to the button text to indicate
        # that the copy was done.
        button.set_label(MSG_COPY_TO_CLIPBOARD + ' *')
        threading.Timer(5.0, lambda b: b.set_label(MSG_COPY_TO_CLIPBOARD),
                        button).start()


    def on_click_show_pedigrees(self, _button):
        """
        Show pedigrees window.
        """
        PedigreesWindow(self.dbstate.db,
                        self.uistate,
                        self.active_handle)


    def on_button_toggled(self, button, which):
        """
        A view style radio button is selected.
        """
        if button.get_active():
            self.view_style = which
            self.get_option(MSG_VIEW_STYLE).set_value(which)
            self.refresh_content()

            self.view_style = self.get_option(MSG_VIEW_STYLE).get_value()
            self.gui.data = [self.view_style]
            self.update()


    def on_activate_link(self, _label, href):
        """
        Called when the user clicks on a link within the gramplet.
        Based on the href, either a new active person is selected,
        or the descendants window is displayed.
        """
        # Parse out href
        href_items = href.split()
        href_type = href_items[0]

        if href_type == 'P':
            # Switch active person
            person_handle = href_items[1]
            Gdk.threads_add_idle(GLib.PRIORITY_DEFAULT_IDLE,
                                 self.uistate.set_active,
                                 person_handle, 'Person')

        elif href_type == 'N':
            # Display descendants window
            pedigree = self.pedigrees[int(href_items[1])]
            rellist = list()
            for item in href_items[2:]:
                nums = [int(x) for x in item.split(',')]
                rellist.append(nums)

            DescendantsWindow(self.dbstate.db,
                              self.uistate,
                              self.active_handle,
                              pedigree, rellist)

        return True


    def _get_pedigree_for_person(self, person_handle):
        """
        Get pedigree for active person
        """
        pedigree = Pedigree.make_pedigree(self.dbstate.db, person_handle)
        self.pedigrees.append(pedigree)
        return pedigree


    def _get_pedigrees_for_spouses(self, person_handle):
        """
        Get pedigrees for spouses of specified person
        """
        spouse_list = list()

        spouses = get_spouses(self.dbstate.db, person_handle)
        if not spouses:
            return spouse_list

        # Go through spouses
        for spouse_handle in spouses:
            # Get pedigree for person and spouse.
            pedigree = Pedigree.make_pedigree(self.dbstate.db,
                                              person_handle,
                                              spouse_handle)
            self.pedigrees.append(pedigree)
            spouse_list.append((spouse_handle, pedigree))

        return spouse_list


    def main(self): # return false finishes
        """
        Generator which will be run in the background.

        Overrides method in class Gramplet.
        """

        Pedigree.clear_ancestor_cache()
        self.pedigrees = list()

        active_handle = self.get_active('Person')
        if not active_handle:
            return

        self.active_handle = active_handle

        # Do we have cached data for this person already?
        cached_data = self.cache.find(active_handle)
        if cached_data:
            # Let's use cached data instead of recomputing it
            self.title_section.set_markup(cached_data[0])
            self.ped_collapse_section.set_markup(cached_data[1])
            self.cosanguinuity_section.set_markup(cached_data[2])
            yield False

        # Get pedigree for active person
        active_pedigree = self._get_pedigree_for_person(active_handle)
        yield True

        # Get pedigrees for spouses
        spouse_pedigrees = self._get_pedigrees_for_spouses(active_handle)
        yield True

        # Format data for output
        data_formatter = CosFormatter(self.dbstate.db,
                                      active_handle,
                                      active_pedigree,
                                      spouse_pedigrees)

        # Print out name of active person
        title = data_formatter.get_title()
        self.title_section.set_markup(title)

        # Get pedigree collapse section
        ped_coll_section = data_formatter.get_pedigree_collapse()
        self.ped_collapse_section.set_markup(ped_coll_section)
        yield True

        # Get spousal cosanguinuity section
        cosanguinuity_section = data_formatter.get_cosanguinuity()
        self.cosanguinuity_section.set_markup(cosanguinuity_section)

        # Save data in cache
        self.cache.add(active_handle,
                       (title, ped_coll_section, cosanguinuity_section))


#------------------------------#
#                              #
# DescendantsWindow class      #
#                              #
#------------------------------#
class DescendantsWindow(Gtk.Window):
    """
    DescendantsWindow

    A window showing the descendants of a given person.
    """

    def __init__(self, db, uistate, active_handle, pedigree, rellist):
        """
        """
        self.db = db
        self.pedigree = pedigree
        self.uistate = uistate
        self.active_handle = active_handle

        Gtk.Window.__init__(self, title=MSG_DESCENDANTS)
        self.set_default_size(800, 600)

        # Get colors
        colors_male = color_graph_box(False, Person.MALE)
        colors_female = color_graph_box(False, Person.FEMALE)
        PersonLabel.set_colors(colors_male, colors_female)

        # Identify top people in report
        if len(rellist[0]) > 2:
            ancestors = [pedigree.get_ancestor_by_number(rellist[0][0]),
                         pedigree.get_ancestor_by_number(rellist[0][2])]
        else:
            ancestors = [pedigree.get_ancestor_by_number(rellist[0][0])]

        # Get names of top people in report
        anc_names = list()
        for anc in ancestors:
            pers = anc.get_person_handle()
            anc_names.append(CosFormatter.format_person(self.db, pers,
                                                        split=True))

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.homogenous = False
        box.set_border_width(0)

        # Make content window
        content = Gtk.ScrolledWindow()
        if len(rellist) > 1:
            tabbed = Gtk.Notebook()
            count = 1
            for one in rellist:
                desc_grid = Gtk.Grid()
                desc_grid.set_border_width(10)
                desc_grid.set_row_spacing(0)
                desc_grid.set_column_spacing(0)
                self.fill_rellist(desc_grid, ancestors, anc_names, one)
                tabbed.append_page(desc_grid, Gtk.Label(label=str(count)))
                count += 1
            content.add(tabbed)

        else:
            desc_grid = Gtk.Grid()
            desc_grid.set_border_width(10)
            desc_grid.set_row_spacing(0)
            desc_grid.set_column_spacing(0)
            self.fill_rellist(desc_grid, ancestors, anc_names, rellist[0])
            content.add(desc_grid)

        box.pack_start(content, expand=True, fill=True, padding=5)

        # Button bar
        button_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        close_button = Gtk.Button.new_with_label(MSG_CLOSE)
        close_button.connect('clicked', lambda x: self.close())
        button_bar.pack_start(close_button, False, False, 5)

        box.pack_start(button_bar, expand=False, fill=False, padding=5)

        self.add(box)
        self.show_all()


    def fill_rellist(self, desc_grid, ancestors, anc_names, rels):
        """
        Fill content of descendant grid.
        """

        # Get descendant numbers down both lines of descent
        adesc = list(Pedigree.iter_down_descendants(rels[0]))
        bdesc = list(Pedigree.iter_down_descendants(rels[1]))

        # Arrange the lines of descent so the final couple has the
        # male on the left side of the chart
        aix = -1
        while adesc[aix] == bdesc[aix]:
            aix -= 1
        if aix and adesc[aix] % 2 == 1:
            (adesc, bdesc) = (bdesc, adesc)

        # If lines of descent are different lengths, pad beginning of the
        # shorter list
        alen = len(adesc)
        blen = len(bdesc)
        afirst = adesc[0]
        bfirst = bdesc[0]
        if alen < blen:
            adesc = [0] * (blen-alen) + adesc
        elif alen > blen:
            bdesc = [0] * (alen-blen) + bdesc

        line = 0

        # Do we have one or two common ancestors?
        if len(anc_names) == 2:
            # We have two common ancestors
            lab = PersonLabel(anc_names[0], ancestors[0].is_male(),
                              self.on_activate_link)
            desc_grid.attach(lab, 1, line, 3, 1)
            desc_grid.attach(CharLabel("══"), 4, line, 1, 1)
            lab = PersonLabel(anc_names[1], ancestors[1].is_male(),
                              self.on_activate_link)
            desc_grid.attach(lab, 5, line, 3, 1)

        else:
            # We have one common ancestor. Determine other parents from
            # the first child down each path.
            prim_is_male = ancestors[0].is_male()

            aspouse = (afirst*2+1) if prim_is_male else (afirst*2)
            anc = self.pedigree.get_ancestor_by_number(aspouse)
            pers = anc.get_person_handle()
            aspouse_name = CosFormatter.format_person \
                               (self.db, pers, split=True)

            bspouse = (bfirst*2+1) if prim_is_male else (bfirst*2)
            anc = self.pedigree.get_ancestor_by_number(bspouse)
            pers = anc.get_person_handle()
            bspouse_name = CosFormatter.format_person \
                               (self.db, pers, split=True)

            lab = PersonLabel(aspouse_name, (aspouse%2 == 0),
                              self.on_activate_link)
            desc_grid.attach(lab, 0, line, 2, 1)
            desc_grid.attach(CharLabel("══"), 2, line, 1, 1)
            lab = PersonLabel(anc_names[0], ancestors[0].is_male(),
                              self.on_activate_link)
            desc_grid.attach(lab, 3, line, 3, 1)
            desc_grid.attach(CharLabel("══"), 6, line, 1, 1)
            lab = PersonLabel(bspouse_name, (bspouse%2 == 0),
                              self.on_activate_link)
            desc_grid.attach(lab, 7, line, 2, 1)

        line += 1

        # Fill grid with descendants
        for (anc_num_a, anc_num_b) in zip(adesc, bdesc):
            alabel = None
            if anc_num_a:
                aanc = self.pedigree.get_ancestor_by_number(anc_num_a)
                apers = aanc.get_person_handle()
                if not apers:
                    break
                aname = CosFormatter.format_person(self.db, apers, split=True)
                if apers == self.active_handle:
                    aname = '<span weight="bold">%s</span>' % aname
                alabel = PersonLabel(aname, aanc.is_male(),
                                     self.on_activate_link)

            blabel = None
            if anc_num_b and anc_num_b != anc_num_a:
                banc = self.pedigree.get_ancestor_by_number(anc_num_b)
                bpers = banc.get_person_handle()
                bname = CosFormatter.format_person(self.db, bpers, split=True)
                if bpers == self.active_handle:
                    bname = '<span weight="bold">%s</span>' % bname
                blabel = PersonLabel(bname, banc.is_male(),
                                     self.on_activate_link)

            if anc_num_a != anc_num_b:
                if line == 1 and len(anc_names) == 2:
                    desc_grid.attach(CharLabel("│\n────────────┴────────────"),
                                     3, line, 3, 1)
                else:
                    desc_grid.attach(CharLabel('│'), 1, line, 3, 1)
                    desc_grid.attach(CharLabel('│'), 5, line, 3, 1)
                line += 1

                if not alabel:
                    alabel = CharLabel(("│\n" * len(bname.splitlines()))[:-1])
                desc_grid.attach(alabel, 1, line, 3, 1)

                if not blabel:
                    blabel = CharLabel(("│\n" * len(aname.splitlines()))[:-1])
                desc_grid.attach(blabel, 5, line, 3, 1)

                # are these two people a couple?
                if anc_num_a and anc_num_b:
                    if anc_num_a % 2 == 0 and anc_num_a + 1 == anc_num_b:
                        # Add = to indicate married couple
                        desc_grid.attach(CharLabel('══'), 4, line, 1, 1)
            else:
                desc_grid.attach(CharLabel('│'), 4, line, 1, 1)
                line += 1
                desc_grid.attach(alabel, 3, line, 3, 1)

            line += 1


    def on_activate_link(self, _label, href):
        """
        Called when the user clicks on a link within the gramplet.
        A new active person is selected.
        """
        # Parse out href
        href_items = href.split()
        href_type = href_items[0]

        if href_type == 'P':
            # Switch active person
            person_handle = href_items[1]
            Gdk.threads_add_idle(GLib.PRIORITY_DEFAULT_IDLE,
                                 self.uistate.set_active,
                                 person_handle, 'Person')

        return True


class PersonLabel(Gtk.Frame):
    """
    PersonLabel. A Gtk frame with information about a person.
    """

    colors_male = ('#cdf', 'black')
    colors_female = ('#fcd', 'black')
    css = ("""
        .PersonLabelMale { border:2px solid %s; background: %s}
        .PersonLabelFemale { border:2px solid %s; background: %s}
        """ % (colors_male[1], colors_male[0],
               colors_female[1], colors_female[0])) .encode('utf-8')


    def __init__(self, label, male, on_click, *args, **kwargs):
        """
        """
        super().__init__(*args, **kwargs)

        lab = Gtk.Label(label='')
        lab.set_markup(label)
        lab.set_justify(Gtk.Justification.CENTER)
        lab.connect('activate-link', on_click)
        self.add(lab)

        context = self.get_style_context()
        if male:
            context.add_class('PersonLabelMale')
        else:
            context.add_class('PersonLabelFemale')
        self.connect('realize', self.add_provider)


    @classmethod
    def set_colors(cls, colors_male, colors_female):
        """
        Set colors for male and female.
        """
        cls.colors_male = colors_male
        cls.colors_female = colors_female
        cls.css = ("""
            .PersonLabelMale { border:2px solid %s; background: %s}
            .PersonLabelFemale { border:2px solid %s; background: %s}
            """ % (colors_male[1], colors_male[0],
                   colors_female[1], colors_female[0])) .encode('utf-8')


    @classmethod
    def add_provider(cls, widget):
        """
        Add style provider to widget.
        """
        screen = widget.get_screen()
        style = widget.get_style_context()
        provider = Gtk.CssProvider()
        provider.load_from_data(cls.css)
        style.add_provider_for_screen(screen, provider,
                                      Gtk.STYLE_PROVIDER_PRIORITY_USER)


class CharLabel(Gtk.Label):
    """
    A centered bold label widget.
    """

    def __init__(self, text, *args, **kwargs):
        """
        """
        super().__init__(*args, **kwargs)
        self.set_markup('<span size="large" weight="bold">%s</span>' % text)
        self.set_justify(Gtk.Justification.CENTER)


#------------------------------#
#                              #
# PedigreesWindow class        #
#                              #
#------------------------------#
class PedigreesWindow(Gtk.Window):
    """
    PedigreesWindow

    A window showing the pedigrees for the specified people: a person,
    and his/her spouses.
    """

    def __init__(self, db, uistate, person_handle):
        """
        """
        self.db = db
        self.uistate = uistate

        Gtk.Window.__init__(self, title=MSG_DESCENDANTS)
        self.set_default_size(600, 800)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.homogenous = False
        box.set_border_width(0)

        # Notebook for content
        self.notebook = Gtk.Notebook()

        # Pedigree for person
        self.create_page(self.notebook, person_handle)

        # Pedigrees for spouses
        spouse_handle_list = get_spouses(db, person_handle)
        for spouse_handle in spouse_handle_list:
            self.create_page(self.notebook, spouse_handle)

        box.pack_start(self.notebook, expand=True, fill=True, padding=5)

        # Button bar
        button_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        copy_button = Gtk.Button.new_with_label(MSG_COPY_TO_CLIPBOARD)
        copy_button.connect('clicked', self.on_copy_to_clipboard)
        button_bar.pack_start(copy_button, False, False, 5)

        close_button = Gtk.Button.new_with_label(MSG_CLOSE)
        close_button.connect('clicked', lambda x: self.close())
        button_bar.pack_start(close_button, False, False, 5)

        box.pack_start(button_bar, expand=False, fill=False, padding=5)

        self.add(box)
        self.show_all()


    def on_copy_to_clipboard(self, button):
        """
        Copy text of visible panel to clipboard
        """

        page = self.notebook.get_current_page()
        text = self.notebook.get_children()[page] \
                     .get_children()[0] \
                     .get_children()[0].get_text()

        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)

        # Temporarily add '* to the button text to indicate
        # that the copy was done.
        button.set_label(MSG_COPY_TO_CLIPBOARD + ' *')
        threading.Timer(5.0, lambda b: b.set_label(MSG_COPY_TO_CLIPBOARD),
                        button).start()


    def create_page(self, notebook, person_handle):
        """
        Create page and content for notebook
        """
        person_name = CosFormatter.format_person(self.db, person_handle,
                                                 link=False, dates=False)
        person_name = person_name.replace(', ', ",\n")

        scrolled_window = Gtk.ScrolledWindow()

        content = Gtk.Label(label='')
        content.set_valign(Gtk.Align.START)
        content.set_halign(Gtk.Align.START)
        content.set_justify(Gtk.Justification.LEFT)
        content.set_markup(self.get_pedigree_text(person_handle))
        content.connect('activate-link', self.on_activate_link)

        scrolled_window.add(content)
        notebook.append_page(scrolled_window, Gtk.Label(label=person_name))


    def get_pedigree_text(self, person_handle):
        """
        Create text for pedigree
        """
        outstr = SimpleStringBuffer()
        pedigree = Pedigree.make_pedigree(self.db, person_handle)

        for (primary, anc_num, primary_num) in pedigree.get_pedigree():
            if primary:
                ancestor = pedigree.get_ancestor_by_number(anc_num)
                anc_handle = ancestor.get_person_handle()
                anc_name = CosFormatter.format_person(self.db, anc_handle)
                outstr += "%d: %s\n" % (anc_num, anc_name)

            else:
                outstr += "%d: ---> %d\n" % (anc_num, primary_num)

        return str(outstr)


    def on_activate_link(self, _label, href):
        """
        Called when the user clicks on a link within the gramplet.
        A new active person is selected.
        """
        # Parse out href
        href_items = href.split()
        href_type = href_items[0]

        if href_type == 'P':
            # Switch active person
            person_handle = href_items[1]
            Gdk.threads_add_idle(GLib.PRIORITY_DEFAULT_IDLE,
                                 self.uistate.set_active,
                                 person_handle, 'Person')
        return True
