"""
Utility to parse PHP serialized data from Excel files
"""
import re


def php_unserialize_simple(data):
    """
    Parse simple PHP serialized arrays into Python dictionaries.
    Handles format like: a:14:{s:2:"id";s:3:"731";s:4:"name";s:15:"נתן בזיה";...}

    This is a simplified parser focused on the specific format in our data.
    """
    if not data or not isinstance(data, str):
        return None

    # Check if it's a serialized array
    if not data.startswith('a:'):
        return None

    result = {}

    # Pattern to match key-value pairs: s:length:"value"
    # Handles both ASCII and UTF-8 strings
    pattern = r's:(\d+):"([^"]*?)";'

    matches = re.findall(pattern, data)

    # Group matches into key-value pairs
    for i in range(0, len(matches) - 1, 2):
        if i + 1 < len(matches):
            key = matches[i][1]
            value = matches[i + 1][1]
            result[key] = value

    return result


def parse_attendees_list(serialized_data):
    """
    Parse attendees data which contains multiple person records.
    Format: Records separated by | (pipe), each record is a:N:{...}

    Returns a list of dictionaries, each containing person data.
    """
    if not serialized_data or not isinstance(serialized_data, str):
        return []

    # Split by pipe delimiter
    records = serialized_data.split('|')

    persons = []
    for record in records:
        record = record.strip()
        if not record or len(record) < 10:
            continue

        # Parse this record as a PHP serialized array
        person_data = php_unserialize_simple(record)
        if person_data:
            persons.append(person_data)

    return persons


def extract_vote_from_attendee(attendee_dict):
    """
    Extract vote information from an attendee dictionary.
    Returns: 'yes', 'no', 'avoid', or 'missing'

    vote_decision field values:
    1 = yes (בעד)
    2 = no (נגד)
    3 = avoid (נמנע)
    """
    if not attendee_dict:
        return 'missing'

    # Check if missing from meeting/discussion
    if attendee_dict.get('is_missing') == '1' or attendee_dict.get('missing') == '1':
        return 'missing'

    # Check vote_decision field (used in discussions)
    vote_decision = attendee_dict.get('vote_decision', '')
    if vote_decision == '1':
        return 'yes'
    elif vote_decision == '2':
        return 'no'
    elif vote_decision == '3':
        return 'avoid'

    # Check vote field (alternative format)
    vote = attendee_dict.get('vote', '').lower()
    if vote in ['yes', 'no', 'avoid']:
        return vote

    # Hebrew vote values
    if 'בעד' in vote or 'כן' in vote:
        return 'yes'
    elif 'נגד' in vote or 'לא' in vote:
        return 'no'
    elif 'נמנע' in vote or 'הימנע' in vote:
        return 'avoid'

    # Default to missing if unclear
    return 'missing'


if __name__ == '__main__':
    # Test the parser
    test_data = 'a:14:{s:2:"id";s:3:"731";s:4:"name";s:15:"נתן בזיה";s:10:"is_missing";s:1:"0";}'
    result = php_unserialize_simple(test_data)
    print("Test parse result:", result)
