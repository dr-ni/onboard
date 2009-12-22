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

#include <algorithm>
#include <cmath>

#include "lm_merged.h"

using namespace std;


//------------------------------------------------------------------------
// MergedModel - abstract container for one or more component language models
//------------------------------------------------------------------------

struct cmp_results_desc
{
  bool operator() (const LanguageModel::Result& x, const LanguageModel::Result& y)
  { return (y.p < x.p);}
};


void MergedModel::predict(vector<LanguageModel::Result>& results,
                          const vector<wchar_t*>& context,
                          int limit, bool filter_control_words, bool sort)
{
    int i;

    // initialize derived class
    init_merge();

    // merge prediction results of all component models
    ResultsMap m;
    for (i=0; i<(int)components.size(); i++)
    {
        // Ask the derived class if a limit on the number of results
        // is allowed. Otherwise assume a limit would change the
        // outcome and get all results.
        // Setting a limit requires sorting of results by probabilities.
        // Skip sorting for performance reasons if there is no limit.
        bool can_limit = can_limit_components();

        // get prediction from the component model
        vector<Result> rs;
        components[i]->predict(rs, context,
                           can_limit ? limit : -1, // limit number of results
                           filter_control_words,
                           can_limit               // sort (by decreasing prob)
                          );

        merge(m, rs, i);
    }

    // copy map to the results vector
    results.resize(0);
    results.reserve(m.size());
    ResultsMap::iterator mit;
    for (mit=m.begin(); mit != m.end(); mit++)
    {
        Result result = {mit->first, mit->second};
        results.push_back(result);
    }

    if (sort)
    {
        // sort by descending probabilities
        cmp_results_desc cmp_results;
        std::stable_sort(results.begin(), results.end(), cmp_results);
    }

    // find final result size
    int result_size = results.size();
    if (limit >= 0 && limit < (int)results.size())
        result_size = limit;

    // give derived classes a chance to normalize the final probabilities
    normalize(results, result_size);

    // limit results, can't really do this earlier
    if (result_size < (int)results.size())
        results.resize(result_size);
}

//------------------------------------------------------------------------
// OverlayModel - merge by overlaying language models
//------------------------------------------------------------------------
// Merges component models by stacking them on top of each other.
// Existing words in later language models replace the probabilities of
// earlier language models. The order of language models is important,
// the last probability found for a word wins.

// merge vector of ngram probabilities
void OverlayModel::merge(ResultsMap& dst, const vector<Result>& values,
                              int model_index)
{
    vector<Result>::const_iterator it;
    for (it=values.begin(); it != values.end(); it++)
    {
        const wchar_t* word = it->word;
        double p = it->p;

        ResultsMap::iterator mit = dst.insert(dst.begin(),
                                   pair<const wchar_t*, double>(word, 0.0));
        mit->second = p;
    }
}

// merge single ngram
double OverlayModel::get_probability(const wchar_t* const* ngram, int n)
{
    double p = 0.0;
    if (n)
    {
        for (int i=0; i<(int)components.size(); i++)
        {
            if (dictionary.contains(ngram[n-1]))
                p = get_probability(ngram, n);
        }
    }
    return p;
}


//------------------------------------------------------------------------
// LinintModel - linearly interpolate language models
//------------------------------------------------------------------------

void LinintModel::init_merge()
{
    // pad weights with default value in case there are too few entries
    weights.resize(components.size(), 1.0);

    // precalculate divisor
    weight_sum = 0.0;
    for (int i=0; i<(int)components.size(); i++)
        weight_sum += weights[i];
}

// interpolate vector of ngrams
void LinintModel::merge(ResultsMap& dst, const vector<Result>& values,
                              int model_index)
{
    double weight = weights[model_index] / weight_sum;

    vector<Result>::const_iterator it;
    for (it=values.begin(); it != values.end(); it++)
    {
        const wchar_t* word = it->word;
        double p = it->p;

        ResultsMap::iterator mit = dst.insert(dst.begin(),
                                   pair<const wchar_t*, double>(word, 0.0));
        mit->second += weight * p;
    }
}

// interpolate probabilities of a single ngram
double LinintModel::get_probability(const wchar_t* const* ngram, int n)
{
    init_merge();

    double p = 0.0;
    for (int i=0; i<(int)components.size(); i++)
    {
        double weight = weights[i] / weight_sum;
        p += weight * get_probability(ngram, n);
    }

    return p;
}


//------------------------------------------------------------------------
// LoglinintModel - log-linear interpolation of language models
//------------------------------------------------------------------------
void LoglinintModel::init_merge()
{
    // pad weights with default value in case there are too few entries
    weights.resize(components.size(), 1.0);
}

// interpolate prediction results vector
void LoglinintModel::merge(ResultsMap& dst, const vector<Result>& values,
                              int model_index)
{
    double weight = weights[model_index];

    vector<Result>::const_iterator it;
    for (it=values.begin(); it != values.end(); it++)
    {
        const wchar_t* word = it->word;
        double p = it->p;

        ResultsMap::iterator mit = dst.insert(dst.begin(),
                                   pair<const wchar_t*, double>(word, 1.0));
        mit->second *= pow(p, weight);
    }
}

void LoglinintModel::normalize(vector<Result>& results, int result_size)
{
    // The normalization factor for log-linear interpolation is hard to come by.
    // -> Normalize the final limited results instead.
    double psum = 0.0;
    vector<Result>::iterator it;
    for(it=results.begin(); it!=results.end(); it++)
        psum += (*it).p;

    for(it=results.begin(); it!=results.begin()+result_size; it++)
        (*it).p *= 1.0/psum;
}

// interpolate single ngram probabilities
// Without normalization for performance reasons!
// -> can't feed the result into yet another interpolation
double LoglinintModel::get_probability(const wchar_t* const* ngram, int n)
{
    init_merge();

    double p = 1.0;
    for (int i=0; i<(int)components.size(); i++)
    {
        double weight = weights[i];
        p *= pow(get_probability(ngram, n), weight);
    }

    return p;
}

