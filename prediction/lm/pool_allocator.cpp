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

#include <stdint.h>
#include <stdio.h>
#include <assert.h>
#include <cstring>
#include <set>
#include <map>
#include <algorithm>

#ifndef ALEN
#define ALEN(a) ((int)(sizeof(a)/sizeof(*a)))
#endif

#define USE_POOL_ALLOCATOR

using namespace std;

extern void* HeapAlloc(size_t size);
extern void HeapFree(void* p);

#pragma pack(2)
class Slab
{
};

class SlabCtl
{
    public:
        #ifndef NDEBUG
        size_t item_size;
        class ItemPool* item_pool;
        #endif
        void* free_list;
        uint32_t num_used;
};
#pragma pack()

class ItemPool
{
    public:
        ItemPool()
        {
            item_size = 0;
            slab_size = 0;
            items_per_slab = 0;
        }

        ItemPool(size_t size, size_t _slab_size)
        {
            item_size = size;
            slab_size = _slab_size;
            items_per_slab = (slab_size - sizeof(SlabCtl)) / item_size;
        }

        void* alloc_item(map<Slab*, ItemPool*>& slabmap)
        {
            Slab* slab = NULL;
            if (partial.empty())   // no partial slabs there?
            {
                // allocate a new slab
                slab = new_slab();
                if (!slab)
                    return NULL;
                partial.insert(slab);
                slabmap[slab] = this;
            }
            else
            {
                slab = *partial.begin();
            }

            // allocate item in slab
            void* p = alloc_slab_item(slab);  // always succeeds

            // slab full?
            if (!*get_free_list(slab))
            {
                // move slab from partial to full list
                partial.erase(slab);
                full.insert(slab);
                //printf("slab full: slab=%p item_size=%zu items=%zu\n", slab, item_size, items_per_slab);
            }

            return p;
        }

        void free_item(void* p, map<Slab*, ItemPool*>& slabmap)
        {
            // looking for containing slab, not the one after it
            //void* key = (void*)(((uint8_t*)p) - slab_size);

            Slab* slab = NULL;
            set<Slab*>::iterator it;

            // try full slabs first
            if(!full.empty())
            {
                it = full.upper_bound((Slab*)p);
                if (it != full.begin())
                {
                    it--;
                    if ((((uint8_t*)*it) + slab_size) >= p)
                        slab = *it;
                }
            }

            // then partial slabs
            if(!slab && !partial.empty())
            {
                it = partial.upper_bound((Slab*)p);
                if (it != partial.begin())
                {
                    it--;
                    if ((((uint8_t*)*it) + slab_size) >= p)
                        slab = *it;
                }
            }

            if(!slab)
            {
                printf("PoolAllocator: no slab found for item size %zd while freeing %p\n", item_size, p);
                assert(false);
                return;
            }

            // slab full?
            SlabCtl* ctl = get_slab_ctl(slab);
            if (!ctl->free_list)
            {
                // move slab from full to partial list
                full.erase(slab);
                partial.insert(slab);
                #ifndef NDEBUG
                //printf("full slab becomes partially full: slab=%p item_size=%zu items=%zu\n", slab, item_size, items_per_slab);
                #endif
            }

            // free item
            if (free_slab_item(slab, p) == 0)
            {
                // all items freed -> delete slab
                #ifndef NDEBUG
                printf("freeing slab %p item_size=%zu items=%zu\n", slab, item_size, items_per_slab);
                #endif
                partial.erase(slab);
                slabmap.erase(slab);
                HeapFree(slab);
            }
        }

        Slab* new_slab()
        {
            // free items must be large enough for an item pointer
            // -> minimum item size = 8 byte on amd_64
            assert(item_size >= sizeof(void*));

            Slab* slab = (Slab*) HeapAlloc(slab_size);
            if (!slab)
                return NULL;

            #ifndef NDEBUG
            SlabCtl* ctl = get_slab_ctl(slab);
            ctl->item_size = item_size;
            ctl->item_pool = this;
            #endif

            SlabCtl* ctl = get_slab_ctl(slab);
            ctl->num_used = 0;

            // initialize the free list
            void** p = &ctl->free_list; // start of free list
            for (size_t i=0; i<items_per_slab; i++)
            {
                *p = ((uint8_t*)slab) + item_size*i;
                p = (void**)*p;
            }
            *p = NULL;  // end of the free list
            assert(slab == (Slab*)p);

            return slab;
        }

        void* alloc_slab_item(Slab* slab)
        {
            SlabCtl* ctl = get_slab_ctl(slab);
            void** plist = &ctl->free_list;
            void* p = *plist;
            *plist = *(void**)p;
            ctl->num_used++;
            return p;
        }

        size_t free_slab_item(Slab* slab, void* item)
        {
            // must be from the address range of the slab
            assert((uint8_t*)slab <= item &&
                    item < ((uint8_t*)slab) + slab_size - sizeof(SlabCtl));

            // must be start of an item
            assert(size_t((uint8_t*)item - (uint8_t*)slab)/item_size*item_size ==
                   size_t((uint8_t*)item - (uint8_t*)slab));

            // must be the right type of slab
            assert(get_slab_ctl(slab)->item_size == item_size);
            assert(get_slab_ctl(slab)->item_pool == this);

            #ifndef NDEBUG
            memset(item, 0x55, item_size);
            #endif

            SlabCtl* ctl = get_slab_ctl(slab);
            void** plist = &ctl->free_list;
            *(void**)item = *plist;
            *plist = item;
            ctl->num_used--;
            return ctl->num_used;
        }

        bool is_in_slab(Slab* slab, void* p)
        {
            return (uint8_t*)slab <= p &&
                    p < ((uint8_t*)slab) + slab_size - sizeof(SlabCtl);
        }

        SlabCtl* get_slab_ctl(Slab* slab)
        {
            return (SlabCtl*)(((uint8_t*)slab) + slab_size - sizeof(SlabCtl));
        }

        // get start of free list
        void** get_free_list(Slab* slab)
        {
            //return (void**)(((uint8_t*)slab) + slab_size - sizeof(uint32_t*));
            return &get_slab_ctl(slab)->free_list;
        }

    private:
        friend class PoolAllocator;
        size_t item_size;
        size_t items_per_slab;
        size_t slab_size;
        set<Slab*> partial;
        set<Slab*> full;
};

class PoolAllocator
{
    public:
        PoolAllocator()
        {
            memset(pools, 0, sizeof(pools));
        }
        ~PoolAllocator()
        {
            for (int i=0; i<ALEN(pools); i++)
                if (pools[i])
                    HeapFree(pools[i]);
        }

        static PoolAllocator* instance()
        {
            static PoolAllocator allocator;
            return &allocator;
        }

        void* alloc(size_t size)
        {
            //assert(size/4*4 == size);   // must be multiple of 4
            //size_t bin = size/4;
            size_t bin = size;
            if (bin < ALEN(pools))
            {
                ItemPool*& pool = pools[bin];
                if (!pool)
                {
                    size_t page = 4096;
                    size_t n = size * 10;
                    size_t slab_size = ((n + page-1) / page * page);
                    pool = (ItemPool*)HeapAlloc(sizeof(ItemPool));
                    pool = new(pool) ItemPool(size, slab_size);
                }
                return pool->alloc_item(slabmap);
            }
            else
            {
                //printf("HeapAlloc size=%zd\n", size);
                return HeapAlloc(size);
            }
        }

        void free(void* p)
        {
            // try full slabs first
            if(!slabmap.empty())
            {
                map<Slab*, ItemPool*>::iterator it;
                it = slabmap.upper_bound((Slab*)p);
                if (it != slabmap.begin())
                {
                    it--;
                    ItemPool* pool = it->second;
                    if (pool->is_in_slab(it->first, p))
                    {
                        pool->free_item(p, slabmap);
                        return;
                    }
                }
            }

            // hope it's a large block and delegate to heap free()
            HeapFree(p);
        }

    private:
        ItemPool* pools[4096];
       // map<size_t, ItemPool> sizemap;  //
        map<Slab*, ItemPool*> slabmap;  // find slab from pointer
};

#ifdef USE_POOL_ALLOCATOR
void* MemAlloc(size_t size)
{
    return PoolAllocator::instance()->alloc(size);
}

void MemFree(void* p)
{
    return PoolAllocator::instance()->free(p);
}
#else
void* MemAlloc(size_t size)
{
    return HeapAlloc(size);
}

void MemFree(void* p)
{
    return HeapFree(p);
}
#endif


