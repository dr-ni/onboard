/*
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

Author: marmuta <marmvta@gmail.com>
*/

#include "lm_dynamic.h"

using namespace std;

//------------------------------------------------------------------------
// DynamicModelBase - non-template abstract base class of all DynamicModels
//------------------------------------------------------------------------

// return a list of word ids to be considered during the prediction
void DynamicModelBase::get_candidates(const wchar_t* prefix,
                                      std::vector<WordId>& wids,
                                      bool filter_control_words,
                                      bool case_sensitive)
{
    int min_wid = filter_control_words ? NUM_CONTROL_WORDS : 0;
    if (prefix && wcslen(prefix))
    {
        dictionary.prefix_search(prefix, wids, min_wid, case_sensitive);

        // candidate word indices have to be sorted for binsearch in kneser-ney
        sort(wids.begin(), wids.end());
    }
    else
    {
        int size = dictionary.get_num_word_types();
        wids.reserve(size);
        for (int i=min_wid; i<size; i++)
            wids.push_back(i);
    }
}

