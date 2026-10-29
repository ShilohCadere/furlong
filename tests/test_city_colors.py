"""Identity and transfer direction must be stable across route order."""
import unittest
from city_colors import city_color, route_colors


class CityColorTests(unittest.TestCase):
    def test_known_cities_and_airports_share_identities(self):
        groups = {
            'dublin': ['Dublin', ' DUB ', 'Dublin Airport'],
            'galway': ['Galway', 'Shannon Airport', 'SNN'],
            'edinburgh': ['Edinburgh', 'EDI'],
            'inverness': ['Inverness', 'INV', 'Glasgow'],
            'london': ['London', 'LHR', 'LGW', 'London Heathrow'],
            'home': ['STL', 'St. Louis'],
        }
        for key, names in groups.items():
            for name in names:
                self.assertEqual(city_color(name), key)
            self.assertEqual([city_color(n) for n in reversed(names)], [key]*len(names))

    def test_transfer_direction_and_descriptive_labels(self):
        self.assertEqual(route_colors('Dublin → Galway'), ('dublin', 'galway'))
        self.assertEqual(route_colors('Galway → Dublin'), ('galway', 'dublin'))
        self.assertEqual(route_colors('Scotland rail', fallback='ScotRail Inverness to Edinburgh — official tickets'), ('inverness', 'edinburgh'))
        self.assertEqual(route_colors('Ireland transfers', fallback='Expressway 51 — Shannon Airport to Galway'), ('galway', 'galway'))

    def test_explicit_airports_ignore_airline_and_layover_text(self):
        self.assertEqual(route_colors('British Airways via London', 'STL', 'DUB'), ('home', 'dublin'))
        self.assertEqual(route_colors('Whatever route label', 'SNN', 'EDI'), ('galway', 'edinburgh'))
        self.assertEqual(route_colors('Whatever route label', 'EDI', 'SNN'), ('edinburgh', 'galway'))

    def test_unknown_values_are_neutral_not_arbitrary_css(self):
        for value in [None, '', 'Regional transportation', '<script>', 'New Dublinshire']:
            self.assertEqual(city_color(value), 'neutral')
        self.assertEqual(route_colors('Unknown service'), ('neutral', 'neutral'))
